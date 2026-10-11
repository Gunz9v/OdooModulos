/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const QUEUE_KEY = "salesperson_route_tracking.queue.v1";

function makeUuid() {
    if (globalThis.crypto?.randomUUID) {
        return globalThis.crypto.randomUUID();
    }
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function serverDateTime(date) {
    return date.toISOString().replace("T", " ").slice(0, 19);
}

export class RouteTracker extends Component {
    static template = "salesperson_route_tracking.RouteTracker";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            active: false,
            sessionId: false,
            status: false,
            name: "",
            pointCount: 0,
            distanceKm: 0,
            lastPositionAt: false,
            gpsStatus: "inactive",
            gpsMessage: "GPS detenido",
            queueCount: this.readQueue().length,
        });
        this.watchId = false;
        this.flushTimer = false;
        this.onlineHandler = () => this.flushQueue();
        onMounted(() => this.initialize());
        onWillUnmount(() => this.cleanup());
    }

    async initialize() {
        try {
            this.applyPayload(await this.orm.call("salesperson.route.session", "tracking_state", []));
            if (this.state.active && this.state.status === "running") {
                this.startGpsWatch();
            }
            globalThis.addEventListener("online", this.onlineHandler);
            this.flushTimer = globalThis.setInterval(() => this.flushQueue(), 60000);
            await this.flushQueue();
        } catch (error) {
            this.notification.add("No se pudo consultar el estado del recorrido.", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    applyPayload(payload) {
        this.state.active = Boolean(payload.active);
        this.state.sessionId = payload.session_id || false;
        this.state.status = payload.state || false;
        this.state.name = payload.name || "";
        this.state.pointCount = payload.point_count || 0;
        this.state.distanceKm = payload.distance_km || 0;
        this.state.lastPositionAt = payload.last_position_at || false;
    }

    async startTracking() {
        if (!navigator.geolocation) {
            this.notification.add("Este dispositivo no ofrece geolocalización.", { type: "danger" });
            return;
        }
        this.state.loading = true;
        try {
            this.applyPayload(await this.orm.call("salesperson.route.session", "start_tracking", []));
            this.startGpsWatch();
            this.notification.add("Recorrido iniciado. Mantenga Odoo abierto.", { type: "success" });
        } finally {
            this.state.loading = false;
        }
    }

    async pauseTracking() {
        await this.flushQueue();
        this.applyPayload(
            await this.orm.call("salesperson.route.session", "pause_tracking", [this.state.sessionId])
        );
        this.stopGpsWatch("GPS pausado");
    }

    async resumeTracking() {
        this.applyPayload(await this.orm.call("salesperson.route.session", "start_tracking", []));
        this.startGpsWatch();
    }

    async finishTracking() {
        await this.flushQueue();
        this.applyPayload(
            await this.orm.call("salesperson.route.session", "finish_tracking", [this.state.sessionId])
        );
        this.stopGpsWatch("Recorrido finalizado");
        this.notification.add("Recorrido finalizado.", { type: "success" });
    }

    startGpsWatch() {
        if (this.watchId !== false || !navigator.geolocation) {
            return;
        }
        this.state.gpsStatus = "waiting";
        this.state.gpsMessage = "Esperando señal GPS…";
        this.watchId = navigator.geolocation.watchPosition(
            (position) => this.onPosition(position),
            (error) => this.onPositionError(error),
            { enableHighAccuracy: true, maximumAge: 15000, timeout: 30000 }
        );
    }

    stopGpsWatch(message = "GPS detenido") {
        if (this.watchId !== false && navigator.geolocation) {
            navigator.geolocation.clearWatch(this.watchId);
        }
        this.watchId = false;
        this.state.gpsStatus = "inactive";
        this.state.gpsMessage = message;
    }

    onPosition(position) {
        const coords = position.coords;
        const queue = this.readQueue();
        queue.push({
            uuid: makeUuid(),
            recorded_at: serverDateTime(new Date(position.timestamp || Date.now())),
            latitude: coords.latitude,
            longitude: coords.longitude,
            accuracy: coords.accuracy,
            altitude: coords.altitude,
            speed: coords.speed,
            heading: coords.heading,
            source: "browser",
        });
        this.writeQueue(queue);
        this.state.gpsStatus = "active";
        this.state.gpsMessage = `GPS activo · precisión ${Math.round(coords.accuracy || 0)} m`;
        this.state.lastPositionAt = serverDateTime(new Date());
        if (queue.length >= 10) {
            this.flushQueue();
        }
    }

    onPositionError(error) {
        const messages = {
            1: "Permiso GPS denegado. Habilítelo en el navegador.",
            2: "La ubicación no está disponible.",
            3: "El GPS tardó demasiado en responder.",
        };
        this.state.gpsStatus = "error";
        this.state.gpsMessage = messages[error.code] || "No se pudo leer el GPS.";
    }

    async flushQueue() {
        const queue = this.readQueue();
        if (!queue.length || !this.state.sessionId || !navigator.onLine) {
            this.state.queueCount = queue.length;
            return;
        }
        try {
            const batch = queue.slice(0, 100);
            const payload = await this.orm.call("salesperson.route.session", "ingest_points", [
                this.state.sessionId,
                batch,
            ]);
            this.writeQueue(queue.slice(batch.length));
            this.applyPayload(payload);
            if (this.readQueue().length) {
                globalThis.setTimeout(() => this.flushQueue(), 300);
            }
        } catch (error) {
            this.state.queueCount = queue.length;
        }
    }

    readQueue() {
        try {
            const value = JSON.parse(globalThis.localStorage.getItem(QUEUE_KEY) || "[]");
            return Array.isArray(value) ? value : [];
        } catch {
            return [];
        }
    }

    writeQueue(queue) {
        globalThis.localStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
        this.state.queueCount = queue.length;
    }

    cleanup() {
        this.stopGpsWatch();
        if (this.flushTimer) {
            globalThis.clearInterval(this.flushTimer);
        }
        globalThis.removeEventListener("online", this.onlineHandler);
    }
}

registry.category("actions").add("salesperson_route_tracker", RouteTracker);

