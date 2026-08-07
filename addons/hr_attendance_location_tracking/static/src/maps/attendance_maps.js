/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadCSS, loadJS } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const LEAFLET_JS = "/hr_attendance_location_tracking/static/lib/leaflet/leaflet.js";
const LEAFLET_CSS = "/hr_attendance_location_tracking/static/lib/leaflet/leaflet.css";

function popupNode(lines) {
    const container = document.createElement("div");
    for (const [label, value] of lines) {
        const row = document.createElement("div");
        const strong = document.createElement("strong");
        strong.textContent = `${label}: `;
        row.append(strong, document.createTextNode(value || "-"));
        container.appendChild(row);
    }
    return container;
}

class AttendanceJourneyMap extends Component {
    static template = "hr_attendance_location_tracking.JourneyMap";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.mapRef = useRef("map");
        this.state = useState({ loading: true, loaded: false, error: false, session: {}, pointCount: 0 });
        onMounted(() => this.load());
        onWillUnmount(() => this.map?.remove());
    }

    async load() {
        try {
            const sessionId = this.props.action?.params?.session_id;
            const [data] = await Promise.all([
                this.orm.call("hr.attendance.location.session", "route_data", [sessionId]),
                loadJS(LEAFLET_JS),
                loadCSS(LEAFLET_CSS),
            ]);
            this.state.session = data.session;
            this.state.pointCount = data.points.length;
            this.state.loaded = true;
            this.renderMap(data.points);
        } catch (error) {
            this.state.error = true;
            this.notification.add("No se pudo cargar el mapa de la jornada.", { type: "danger" });
            console.error(error);
        } finally {
            this.state.loading = false;
        }
    }

    renderMap(points) {
        this.map = L.map(this.mapRef.el);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        }).addTo(this.map);
        if (!points.length) {
            this.map.setView([-12.0464, -77.0428], 11);
            return;
        }
        const coordinates = points.map((point) => [point.latitude, point.longitude]);
        if (coordinates.length === 1) {
            this.map.setView(coordinates[0], 17);
        } else {
            const line = L.polyline(coordinates, { color: "#714B67", weight: 5, opacity: 0.85 }).addTo(this.map);
            this.map.fitBounds(line.getBounds(), { padding: [30, 30], maxZoom: 17 });
        }
        const first = points[0];
        const last = points[points.length - 1];
        L.marker([first.latitude, first.longitude]).addTo(this.map).bindPopup(
            popupNode([["Inicio", first.recorded_at], ["Precision", `${Math.round(first.accuracy || 0)} m`]])
        );
        if (points.length > 1) {
            L.marker([last.latitude, last.longitude]).addTo(this.map).bindPopup(
                popupNode([["Ultima posicion", last.recorded_at], ["Precision", `${Math.round(last.accuracy || 0)} m`]])
            );
        }
    }
}

class AttendanceTeamMap extends Component {
    static template = "hr_attendance_location_tracking.TeamMap";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.mapRef = useRef("map");
        this.state = useState({ loading: true, error: false, employeeCount: 0, refreshedAt: "" });
        this.timer = null;
        this.firstFit = true;
        onMounted(() => this.start());
        onWillUnmount(() => {
            clearInterval(this.timer);
            this.map?.remove();
        });
    }

    async start() {
        try {
            await Promise.all([loadJS(LEAFLET_JS), loadCSS(LEAFLET_CSS)]);
            this.map = L.map(this.mapRef.el).setView([-12.0464, -77.0428], 11);
            L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                maxZoom: 19,
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
            }).addTo(this.map);
            this.layer = L.layerGroup().addTo(this.map);
            await this.refresh();
            this.timer = setInterval(() => this.refresh(), 30000);
        } catch (error) {
            this.state.error = true;
            this.notification.add("No se pudo cargar el mapa del equipo.", { type: "danger" });
            console.error(error);
        } finally {
            this.state.loading = false;
        }
    }

    async refresh() {
        const employees = await this.orm.call("hr.attendance.location.session", "team_map_data", []);
        this.layer.clearLayers();
        const bounds = [];
        for (const employee of employees) {
            const coordinate = [employee.latitude, employee.longitude];
            bounds.push(coordinate);
            const color = employee.age_seconds > 300 ? "#dc3545" : employee.age_seconds > 120 ? "#f0ad4e" : "#28a745";
            L.circle(coordinate, {
                radius: Math.max(employee.accuracy || 0, 5), color, weight: 1, fillOpacity: 0.08,
            }).addTo(this.layer);
            L.circleMarker(coordinate, {
                radius: 9, color: "#ffffff", weight: 2, fillColor: color, fillOpacity: 1,
            }).addTo(this.layer).bindPopup(popupNode([
                ["Empleado", employee.employee],
                ["Dispositivo", employee.device],
                ["Ultima posicion", employee.last_position_at],
                ["Precision", `${Math.round(employee.accuracy || 0)} m`],
            ]));
        }
        this.state.employeeCount = employees.length;
        this.state.refreshedAt = new Date().toLocaleTimeString();
        if (this.firstFit && bounds.length) {
            this.firstFit = false;
            if (bounds.length === 1) this.map.setView(bounds[0], 16);
            else this.map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
        }
    }
}

registry.category("actions").add("attendance_location_journey_map", AttendanceJourneyMap);
registry.category("actions").add("attendance_location_team_map", AttendanceTeamMap);
