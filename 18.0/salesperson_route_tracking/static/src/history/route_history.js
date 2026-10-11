/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadCSS, loadJS } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class RouteHistory extends Component {
    static template = "salesperson_route_tracking.RouteHistory";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.mapRef = useRef("map");
        this.state = useState({ loading: true, loaded: false, error: false, session: {}, pointCount: 0 });
        this.map = null;
        onMounted(() => this.loadRoute());
        onWillUnmount(() => this.map?.remove());
    }

    async loadRoute() {
        const sessionId = this.props.action?.params?.session_id;
        if (!sessionId) {
            this.notification.add("No se indicó el recorrido a mostrar.", { type: "danger" });
            this.state.loading = false;
            return;
        }
        try {
            const [data] = await Promise.all([
                this.orm.call("salesperson.route.session", "route_data", [sessionId]),
                loadJS("/salesperson_route_tracking/static/lib/leaflet/leaflet.js"),
                loadCSS("/salesperson_route_tracking/static/lib/leaflet/leaflet.css"),
            ]);
            this.state.session = data.session;
            this.state.pointCount = data.points.length;
            this.state.loaded = true;
            this.renderMap(data.points);
        } catch (error) {
            this.state.error = true;
            console.error("Unable to load salesperson route map", error);
            this.notification.add("No se pudo cargar el mapa del recorrido.", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    renderMap(points) {
        this.map = L.map(this.mapRef.el, { zoomControl: true });
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&amp;copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        }).addTo(this.map);
        if (!points.length) {
            this.map.setView([-12.0464, -77.0428], 11);
            return;
        }
        const coordinates = points.map((point) => [point.latitude, point.longitude]);
        const line = L.polyline(coordinates, { color: "#714B67", weight: 5, opacity: 0.85 }).addTo(this.map);
        const first = points[0];
        const last = points[points.length - 1];
        L.marker([first.latitude, first.longitude]).addTo(this.map).bindPopup(`Inicio · ${first.recorded_at}`);
        L.marker([last.latitude, last.longitude]).addTo(this.map).bindPopup(`Última posición · ${last.recorded_at}`);
        this.map.fitBounds(line.getBounds(), { padding: [30, 30], maxZoom: 17 });
    }
}

registry.category("actions").add("salesperson_route_history", RouteHistory);
