/**
 * AI Road Damage Mapper - Frontend Integration Script (v3.0 Final Release)
 * Handles REST API requests, Leaflet GIS map plotting, Chart.js analytics,
 * AI priority engine rendering, geolocation handling, and report lifecycle.
 */

// ─── Backend URL Configuration ────────────────────────────────────────────────
// Backend URL resolution order:
//   1. <meta name="api-base-url"> in index.html (explicit cross-origin URL)
//   2. Opened from disk (file://) or a local dev server -> local FastAPI backend
//   3. Otherwise -> same origin (FastAPI serving this SPA, local or production)
// No secrets belong here; the backend URL is a public endpoint.

const API_BASE_URL = (function () {
    // 1) Explicit override for cross-origin production (e.g. Vercel -> Render)
    const metaTag = document.querySelector('meta[name="api-base-url"]');
    const metaValue = metaTag && metaTag.content ? metaTag.content.trim() : "";
    if (metaValue) {
        return metaValue.replace(/\/+$/, ""); // strip trailing slashes
    }

    const protocol = window.location.protocol;
    const port = window.location.port;
    const origin = window.location.origin;

    // 2a) Opened directly from the filesystem (double-clicked index.html)
    if (protocol === "file:") {
        return "http://localhost:8000";
    }

    // 2b) Local development servers (Live Server / Vite / CRA, etc.)
    const DEV_SERVER_PORTS = ["3000", "4200", "5173", "5500", "8080"];
    if (DEV_SERVER_PORTS.includes(port)) {
        return "http://localhost:8000";
    }

    // 3) Served by FastAPI itself (local or production) -> same origin, no CORS
    return origin;
})();

// Optional write-protection key for mutating requests (POST/PATCH/DELETE).
// Leave the <meta name="api-key"> tag EMPTY for local development (no header sent).
// For a protected backend, set it to the SAME value as the backend's API_KEY env var.
// NOTE: this value ships inside the HTML, so it is lightweight abuse protection only,
// NOT a strong secret (see README "Security" section).
const API_KEY = (function () {
    const metaTag = document.querySelector('meta[name="api-key"]');
    return metaTag && metaTag.content ? metaTag.content.trim() : "";
})();

function buildHeaders(extra) {
    const headers = Object.assign({}, extra || {});
    if (API_KEY) {
        headers["X-API-Key"] = API_KEY;
    }
    return headers;
}


// Active Global State
let currentAnalysisResult = null;
let gisMapInstance = null;
let mapMarkersList = [];
let activeReportInModal = null;

// Chart.js Instances
let chartDamageType = null;
let chartSeverity = null;
let chartPriority = null;
let chartStatus = null;
let chartTimeline = null;

// Geolocation state
let activeLocationSource = "none"; // 'gps', 'manual', 'none'

document.addEventListener("DOMContentLoaded", () => {
    initNavigation();
    initHealthCheck();
    initDashboard();
    initImageAnalysis();
    initLocationHandlers();
    initReportsDirectory();
    initModalHandlers();
    initMapSection();
    initAnalyticsSection();

    // Display detected API base URL in footer
    const footerApiUrl = document.getElementById("footer-api-url");
    if (footerApiUrl) {
        footerApiUrl.textContent = API_BASE_URL || window.location.origin;
    }
});

/* ==========================================================================
   1. NAVIGATION & TAB SWITCHING
   ========================================================================== */
function initNavigation() {
    const navButtons = document.querySelectorAll(".nav-btn");
    const tabPanes = document.querySelectorAll(".tab-pane");

    navButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            const targetId = btn.getAttribute("data-target");

            navButtons.forEach((b) => b.classList.remove("active"));
            tabPanes.forEach((pane) => pane.classList.remove("active"));

            btn.classList.add("active");
            const targetPane = document.getElementById(targetId);
            if (targetPane) {
                targetPane.classList.add("active");
            }

            // Tab specific refresh logic
            if (targetId === "tab-dashboard") {
                loadDashboardStats();
            } else if (targetId === "tab-map") {
                setTimeout(() => {
                    refreshGISMap();
                }, 100);
            } else if (targetId === "tab-analytics") {
                loadAnalyticsData();
            } else if (targetId === "tab-reports") {
                loadReportsTable();
            }
        });
    });
}

/* ==========================================================================
   2. SYSTEM HEALTH & MODEL STATUS CHECK
   ========================================================================== */
async function initHealthCheck() {
    const refreshBtn = document.getElementById("refresh-health-btn");
    if (refreshBtn) {
        refreshBtn.addEventListener("click", checkHealth);
    }
    await checkHealth();
}

async function checkHealth() {
    const statusDot = document.getElementById("status-dot");
    const statusText = document.getElementById("status-text");
    const dbBadge = document.getElementById("db-status-badge");
    const modelBadge = document.getElementById("model-status-badge");
    const timestampLabel = document.getElementById("health-timestamp");
    const modelCalloutText = document.getElementById("ai-model-callout-text");

    try {
        const response = await fetch(`${API_BASE_URL}/health`);
        const data = await response.json();

        if (response.ok) {
            statusDot.className = "status-dot status-online";
            statusText.textContent = `Backend: Online (${data.status})`;

            if (data.database === "connected") {
                dbBadge.className = "badge badge-success";
                dbBadge.textContent = "DB: SQLite Connected";
            } else {
                dbBadge.className = "badge badge-danger";
                dbBadge.textContent = "DB: Disconnected";
            }

            // Model Status Check
            if (data.model_status === "available") {
                modelBadge.className = "badge badge-success";
                modelBadge.textContent = "AI Model: Active";
                if (modelCalloutText) {
                    modelCalloutText.innerHTML = "<strong>AI Detection Engine Ready:</strong> Legitimate computer vision model loaded. Full bounding box localization & damage classification active.";
                }
            } else if (data.model_status === "not_configured") {
                modelBadge.className = "badge badge-warning";
                modelBadge.textContent = "AI Model: Not Configured";
                if (modelCalloutText) {
                    modelCalloutText.innerHTML = "<strong>AI Model Unconfigured:</strong> No model file configured at <code>MODEL_PATH</code>. Image upload & REST pipeline active with <code>model_status: not_configured</code>. No fake detections will be generated.";
                }
            } else {
                modelBadge.className = "badge badge-danger";
                modelBadge.textContent = `AI Model: ${data.model_status}`;
                if (modelCalloutText) {
                    modelCalloutText.innerHTML = `<strong>AI Model Warning:</strong> Model status is '${data.model_status}'. Check server logs.`;
                }
            }

            timestampLabel.textContent = `Updated: ${new Date().toLocaleTimeString()}`;
        } else {
            throw new Error("Health check returned non-200 response");
        }
    } catch (err) {
        console.warn("Health check error:", err);
        statusDot.className = "status-dot status-offline";
        statusText.textContent = "Backend: Unavailable";
        dbBadge.className = "badge badge-danger";
        dbBadge.textContent = "DB: Connection Error";
        modelBadge.className = "badge badge-danger";
        modelBadge.textContent = "AI Model: Offline";
        timestampLabel.textContent = "Offline";
    }
}

/* ==========================================================================
   3. DASHBOARD VIEW & REAL STATS
   ========================================================================== */
function initDashboard() {
    const refreshBtn = document.getElementById("dashboard-refresh-reports");
    if (refreshBtn) {
        refreshBtn.addEventListener("click", loadDashboardStats);
    }
    loadDashboardStats();
}

async function loadDashboardStats() {
    try {
        const statsRes = await fetch(`${API_BASE_URL}/statistics`);
        if (statsRes.ok) {
            const stats = await statsRes.json();
            document.getElementById("stat-total").textContent = stats.total_reports || 0;
            document.getElementById("stat-high-priority").textContent = stats.high_priority_count || 0;
            document.getElementById("stat-open").textContent = stats.open_reports_count || 0;
            document.getElementById("stat-reviewed").textContent = stats.reviewed_reports_count || 0;
            document.getElementById("stat-resolved").textContent = stats.resolved_reports_count || 0;
        }

        const reportsRes = await fetch(`${API_BASE_URL}/reports?limit=10`);
        if (reportsRes.ok) {
            const reports = await reportsRes.json();
            renderDashboardTable(reports);
        }
    } catch (err) {
        console.error("Error loading dashboard stats:", err);
    }
}

function renderDashboardTable(reports) {
    const tbody = document.getElementById("dashboard-reports-tbody");
    if (!tbody) return;

    if (!reports || reports.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="empty-state">No reports available yet. Upload a road image in 'Analyze Road' to create your first report.</td></tr>`;
        return;
    }

    tbody.innerHTML = reports.map((r) => {
        const imgMarkup = r.annotated_image_path
            ? `<img src="${API_BASE_URL}/${r.annotated_image_path}" class="table-thumb" alt="Annotated">`
            : r.image_path
            ? `<img src="${API_BASE_URL}/${r.image_path}" class="table-thumb" alt="Original">`
            : `<span class="badge">No image</span>`;

        const locText = (r.latitude !== null && r.longitude !== null)
            ? `📍 ${r.latitude.toFixed(4)}, ${r.longitude.toFixed(4)}`
            : `<span class="badge">Location unavailable</span>`;

        const pLevel = r.priority_level || "LOW";
        const pBadgeClass = pLevel === "HIGH" ? "badge-danger" : pLevel === "MEDIUM" ? "badge-warning" : "badge-success";

        return `
            <tr>
                <td><strong>#${r.id}</strong></td>
                <td>${imgMarkup}</td>
                <td><span class="badge">${r.damage_type || "N/A"}</span></td>
                <td>${getSeverityBadge(r.severity)}</td>
                <td><span class="badge ${pBadgeClass}">${pLevel} (${r.priority_score || 0})</span></td>
                <td>${locText}</td>
                <td>${getStatusBadge(r.status)}</td>
                <td>
                    <button class="btn-sm btn-outline" onclick="openReportModal(${r.id})">Details</button>
                </td>
            </tr>
        `;
    }).join("");
}

/* ==========================================================================
   4. IMAGE ANALYSIS WORKFLOW & PRIORITY ENGINE PREVIEW
   ========================================================================== */
function initImageAnalysis() {
    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("analyze-file-input");
    const form = document.getElementById("analyze-form");
    const saveForm = document.getElementById("save-analysis-form");

    if (dropZone && fileInput) {
        dropZone.addEventListener("click", () => fileInput.click());
        dropZone.addEventListener("dragover", (e) => {
            e.preventDefault();
            dropZone.classList.add("dragover");
        });
        dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
        dropZone.addEventListener("drop", (e) => {
            e.preventDefault();
            dropZone.classList.remove("dragover");
            if (e.dataTransfer.files.length > 0) {
                fileInput.files = e.dataTransfer.files;
                handleImageSelection(e.dataTransfer.files[0]);
            }
        });
        fileInput.addEventListener("change", (e) => {
            if (e.target.files.length > 0) {
                handleImageSelection(e.target.files[0]);
            }
        });
    }

    if (form) {
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (!fileInput.files || fileInput.files.length === 0) {
                showMsg("analyze-response-msg", "Please select a road image file first.", false);
                return;
            }
            await runImageAnalysis(fileInput.files[0]);
        });
    }

    if (saveForm) {
        saveForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            await saveAnalysisToReport();
        });
    }
}

function handleImageSelection(file) {
    const previewContainer = document.getElementById("preview-container");
    const previewImg = document.getElementById("image-preview");

    if (file && previewContainer && previewImg) {
        const reader = new FileReader();
        reader.onload = (e) => {
            previewImg.src = e.target.result;
            previewContainer.style.display = "block";
        };
        reader.readAsDataURL(file);
    }
}

async function runImageAnalysis(file) {
    const submitBtn = document.getElementById("analyze-submit-btn");
    const spinner = document.getElementById("analyze-btn-spinner");
    const btnText = document.getElementById("analyze-btn-text");
    const msgDiv = document.getElementById("analyze-response-msg");
    const resultsPanel = document.getElementById("analysis-results-panel");

    submitBtn.disabled = true;
    spinner.style.display = "inline-block";
    btnText.textContent = "Running AI Computer Vision Detection...";
    msgDiv.style.display = "none";
    resultsPanel.style.display = "none";

    const formData = new FormData();
    formData.append("file", file);

    try {
        const res = await fetch(`${API_BASE_URL}/analyze-image`, {
            method: "POST",
            headers: buildHeaders(), // do NOT set Content-Type: FormData adds it
            body: formData,
        });

        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.detail || "Analysis request failed.");
        }

        currentAnalysisResult = data;
        renderAnalysisResults(data);
        resultsPanel.style.display = "block";
        resultsPanel.scrollIntoView({ behavior: "smooth" });
    } catch (err) {
        console.error("Analysis error:", err);
        showMsg("analyze-response-msg", `Error analyzing image: ${err.message}`, false);
    } finally {
        submitBtn.disabled = false;
        spinner.style.display = "none";
        btnText.textContent = "Analyze Road Image";
    }
}

function renderAnalysisResults(data) {
    // Severity Badge
    const sevBadge = document.getElementById("overall-severity-badge");
    sevBadge.className = `badge ${getSeverityBadgeClass(data.overall_severity)}`;
    sevBadge.textContent = `Overall Severity: ${data.overall_severity}`;

    // Images
    const origImg = document.getElementById("res-original-img");
    const annotImg = document.getElementById("res-annotated-img");
    origImg.src = `${API_BASE_URL}/${data.original_image}`;
    annotImg.src = data.annotated_image ? `${API_BASE_URL}/${data.annotated_image}` : origImg.src;

    // AI Priority Card Preview
    const pScore = document.getElementById("res-priority-score");
    const pBadge = document.getElementById("res-priority-badge");
    const pReason = document.getElementById("res-priority-reason");

    if (pScore && pBadge && pReason) {
        pScore.textContent = `Score: ${data.priority_score || 0} / 100`;
        const pLevel = data.priority_level || "LOW";
        pBadge.textContent = pLevel;
        pBadge.className = `badge ${pLevel === "HIGH" ? "badge-danger" : pLevel === "MEDIUM" ? "badge-warning" : "badge-success"}`;
        pReason.textContent = data.priority_reason || "Calculated priority rationale.";
    }

    // Detections Table
    const tbody = document.getElementById("detections-tbody");
    if (data.detections && data.detections.length > 0) {
        tbody.innerHTML = data.detections.map((d) => `
            <tr>
                <td><strong>${d.damage_type}</strong></td>
                <td>${(d.confidence * 100).toFixed(1)}%</td>
                <td>${getSeverityBadge(d.severity)}</td>
                <td><code>(${d.bounding_box.x1.toFixed(0)}, ${d.bounding_box.y1.toFixed(0)}, ${d.bounding_box.x2.toFixed(0)}, ${d.bounding_box.y2.toFixed(0)})</code></td>
                <td><small>${d.severity_reason || "Assessed distress."}</small></td>
            </tr>
        `).join("");
    } else {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No road damage detected in image frame.</td></tr>`;
    }
}

/* ==========================================================================
   5. LOCATION HANDLING (BROWSER GPS VS MANUAL)
   ========================================================================== */
function initLocationHandlers() {
    const gpsBtn = document.getElementById("use-gps-btn");
    const latInput = document.getElementById("save-lat");
    const longInput = document.getElementById("save-long");

    if (gpsBtn) {
        gpsBtn.addEventListener("click", () => {
            if (!navigator.geolocation) {
                alert("Browser Geolocation is not supported by your browser.");
                return;
            }

            gpsBtn.disabled = true;
            gpsBtn.textContent = "📍 Requesting GPS Location...";

            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const lat = position.coords.latitude;
                    const lng = position.coords.longitude;

                    if (latInput) latInput.value = lat.toFixed(6);
                    if (longInput) longInput.value = lng.toFixed(6);

                    activeLocationSource = "gps";
                    updateLocationSourceTag("Browser GPS", "tag-gps");

                    gpsBtn.disabled = false;
                    gpsBtn.textContent = "📍 Location Updated (Browser GPS)";
                },
                (error) => {
                    console.warn("Geolocation error:", error);
                    let errStr = "Unable to retrieve GPS location.";
                    if (error.code === error.PERMISSION_DENIED) {
                        errStr = "Location permission was denied by user.";
                    } else if (error.code === error.POSITION_UNAVAILABLE) {
                        errStr = "GPS position unavailable.";
                    }
                    alert(errStr);

                    gpsBtn.disabled = false;
                    gpsBtn.textContent = "📍 Use My Location (Browser GPS)";
                }
            );
        });
    }

    [latInput, longInput].forEach((input) => {
        if (input) {
            input.addEventListener("input", () => {
                if (latInput.value || longInput.value) {
                    activeLocationSource = "manual";
                    updateLocationSourceTag("Manual Input", "tag-manual");
                } else {
                    activeLocationSource = "none";
                    updateLocationSourceTag("No location selected", "tag-none");
                }
            });
        }
    });
}

function updateLocationSourceTag(text, className) {
    const tag = document.getElementById("location-source-tag");
    if (tag) {
        tag.textContent = text;
        tag.className = `location-tag ${className}`;
    }
}

async function saveAnalysisToReport() {
    if (!currentAnalysisResult) {
        showMsg("save-analysis-msg", "No active analysis result to save.", false);
        return;
    }

    const latVal = document.getElementById("save-lat").value;
    const longVal = document.getElementById("save-long").value;
    const descVal = document.getElementById("save-desc").value;

    let latitude = latVal ? parseFloat(latVal) : null;
    let longitude = longVal ? parseFloat(longVal) : null;

    // Validate coordinates
    if (latitude !== null && (latitude < -90 || latitude > 90)) {
        showMsg("save-analysis-msg", "Latitude must be between -90 and 90 degrees.", false);
        return;
    }
    if (longitude !== null && (longitude < -180 || longitude > 180)) {
        showMsg("save-analysis-msg", "Longitude must be between -180 and 180 degrees.", false);
        return;
    }

    const saveBtn = document.getElementById("save-report-btn");
    saveBtn.disabled = true;

    // Determine top damage type & confidence
    const detections = currentAnalysisResult.detections || [];
    const topDamage = detections.length > 0 ? detections[0].damage_type : "NO_DAMAGE";
    const topConf = detections.length > 0 ? detections[0].confidence : 0.0;

    const payload = {
        image_path: currentAnalysisResult.original_image,
        annotated_image_path: currentAnalysisResult.annotated_image,
        damage_type: topDamage,
        severity: currentAnalysisResult.overall_severity,
        confidence: topConf,
        latitude: latitude,
        longitude: longitude,
        description: descVal || null,
        priority_score: currentAnalysisResult.priority_score,
        priority_level: currentAnalysisResult.priority_level,
        priority_reason: currentAnalysisResult.priority_reason,
    };

    try {
        const res = await fetch(`${API_BASE_URL}/reports`, {
            method: "POST",
            headers: buildHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify(payload),
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || "Failed to save report.");
        }

        showMsg("save-analysis-msg", `✅ Report #${data.id} saved successfully to SQLite database!`, true);

        // Refresh global statistics and views
        loadDashboardStats();
        loadReportsTable();
        refreshGISMap();
    } catch (err) {
        showMsg("save-analysis-msg", `Error saving report: ${err.message}`, false);
    } finally {
        saveBtn.disabled = false;
    }
}

/* ==========================================================================
   6. REPORTS DIRECTORY & FILTERS
   ========================================================================== */
function initReportsDirectory() {
    const applyBtn = document.getElementById("apply-filters-btn");
    const resetBtn = document.getElementById("reset-filters-btn");
    const createForm = document.getElementById("create-report-form");

    if (applyBtn) applyBtn.addEventListener("click", loadReportsTable);
    if (resetBtn) {
        resetBtn.addEventListener("click", () => {
            document.getElementById("filter-damage-type").value = "";
            document.getElementById("filter-severity").value = "";
            document.getElementById("filter-priority").value = "";
            document.getElementById("filter-status").value = "";
            loadReportsTable();
        });
    }

    if (createForm) {
        createForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            await createManualReport();
        });
    }

    loadReportsTable();
}

async function loadReportsTable() {
    const tbody = document.getElementById("all-reports-tbody");
    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="9" class="empty-state">Loading reports from database...</td></tr>`;

    const dt = document.getElementById("filter-damage-type")?.value || "";
    const sev = document.getElementById("filter-severity")?.value || "";
    const pri = document.getElementById("filter-priority")?.value || "";
    const st = document.getElementById("filter-status")?.value || "";

    const params = new URLSearchParams();
    if (dt) params.append("damage_type", dt);
    if (sev) params.append("severity", sev);
    if (pri) params.append("priority_level", pri);
    if (st) params.append("status", st);

    try {
        const res = await fetch(`${API_BASE_URL}/reports?${params.toString()}`);
        if (!res.ok) throw new Error("Failed to fetch reports.");

        const reports = await res.json();
        renderAllReportsTable(reports);
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="9" class="empty-state error">Error loading reports: ${err.message}</td></tr>`;
    }
}

function renderAllReportsTable(reports) {
    const tbody = document.getElementById("all-reports-tbody");
    if (!tbody) return;

    if (!reports || reports.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" class="empty-state">No matching report records found in database.</td></tr>`;
        return;
    }

    tbody.innerHTML = reports.map((r) => {
        const imgMarkup = r.annotated_image_path
            ? `<img src="${API_BASE_URL}/${r.annotated_image_path}" class="table-thumb" alt="Annotated">`
            : r.image_path
            ? `<img src="${API_BASE_URL}/${r.image_path}" class="table-thumb" alt="Original">`
            : `<span class="badge">No Image</span>`;

        const locText = (r.latitude !== null && r.longitude !== null)
            ? `📍 ${r.latitude.toFixed(4)}, ${r.longitude.toFixed(4)}`
            : `<span class="badge">Location unavailable</span>`;

        const pLevel = r.priority_level || "LOW";
        const pBadgeClass = pLevel === "HIGH" ? "badge-danger" : pLevel === "MEDIUM" ? "badge-warning" : "badge-success";
        const confText = r.confidence !== null ? `${(r.confidence * 100).toFixed(0)}%` : "N/A";
        const dateText = r.timestamp ? new Date(r.timestamp).toLocaleString() : "--";

        return `
            <tr>
                <td><strong>#${r.id}</strong></td>
                <td>${imgMarkup}</td>
                <td><span class="badge">${r.damage_type || "N/A"}</span></td>
                <td>${getSeverityBadge(r.severity)}</td>
                <td>${confText}</td>
                <td><span class="badge ${pBadgeClass}">${pLevel} (${r.priority_score || 0})</span></td>
                <td>${locText}</td>
                <td>${getStatusBadge(r.status)}</td>
                <td><small>${dateText}</small></td>
                <td>
                    <button class="btn-sm btn-outline" onclick="openReportModal(${r.id})">Inspect</button>
                    <button class="btn-sm btn-danger" onclick="deleteReportRecord(${r.id})">Delete</button>
                </td>
            </tr>
        `;
    }).join("");
}

async function createManualReport() {
    const dt = document.getElementById("form-damage-type").value;
    const sev = document.getElementById("form-severity").value;
    const lat = document.getElementById("form-lat").value;
    const lng = document.getElementById("form-long").value;
    const desc = document.getElementById("form-desc").value;

    const payload = {
        damage_type: dt || null,
        severity: sev || null,
        latitude: lat ? parseFloat(lat) : null,
        longitude: lng ? parseFloat(lng) : null,
        description: desc || null,
        status: "NEW",
    };

    try {
        const res = await fetch(`${API_BASE_URL}/reports`, {
            method: "POST",
            headers: buildHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify(payload),
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to create report.");

        showMsg("create-report-msg", `✅ Manual Report #${data.id} created!`, true);
        document.getElementById("create-report-form").reset();
        loadReportsTable();
        loadDashboardStats();
        refreshGISMap();
    } catch (err) {
        showMsg("create-report-msg", `Error: ${err.message}`, false);
    }
}

async function deleteReportRecord(id) {
    if (!confirm(`Are you sure you want to delete Report #${id}?`)) return;

    try {
        const res = await fetch(`${API_BASE_URL}/reports/${id}`, { method: "DELETE", headers: buildHeaders() });
        if (!res.ok) throw new Error("Failed to delete report.");

        loadReportsTable();
        loadDashboardStats();
        refreshGISMap();
    } catch (err) {
        alert(`Error deleting report: ${err.message}`);
    }
}

/* ==========================================================================
   7. INTERACTIVE GIS MAP SECTION (LEAFLET + OPENSTREETMAP)
   ========================================================================== */
function initMapSection() {
    const refreshBtn = document.getElementById("map-refresh-btn");
    const centerBtn = document.getElementById("map-reset-view-btn");

    if (refreshBtn) refreshBtn.addEventListener("click", refreshGISMap);
    if (centerBtn) {
        centerBtn.addEventListener("click", () => {
            if (gisMapInstance && mapMarkersList.length > 0) {
                const group = L.featureGroup(mapMarkersList);
                gisMapInstance.fitBounds(group.getBounds().pad(0.2));
            } else if (gisMapInstance) {
                gisMapInstance.setView([37.7749, -122.4194], 12);
            }
        });
    }
}

function ensureMapInitialized() {
    if (!gisMapInstance) {
        const mapContainer = document.getElementById("gis-map");
        if (!mapContainer) return;

        // Default view set to San Francisco coordinates
        gisMapInstance = L.map("gis-map").setView([37.7749, -122.4194], 12);

        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        }).addTo(gisMapInstance);
    }
}

async function refreshGISMap() {
    ensureMapInitialized();
    if (!gisMapInstance) return;

    // Clear existing markers
    mapMarkersList.forEach((m) => gisMapInstance.removeLayer(m));
    mapMarkersList = [];

    const pinBadge = document.getElementById("map-pin-count-badge");
    const noLocBadge = document.getElementById("map-no-loc-badge");
    const emptyNotice = document.getElementById("map-empty-state-notice");

    try {
        const res = await fetch(`${API_BASE_URL}/reports`);
        if (!res.ok) return;

        const reports = await res.json();
        const geotagged = reports.filter((r) => r.latitude !== null && r.longitude !== null);
        const unmapped = reports.length - geotagged.length;

        if (pinBadge) pinBadge.textContent = `${geotagged.length} Mapped Pins`;
        if (noLocBadge) noLocBadge.textContent = `${unmapped} Location Unavailable`;

        if (geotagged.length === 0) {
            if (emptyNotice) emptyNotice.style.display = "block";
            return;
        } else {
            if (emptyNotice) emptyNotice.style.display = "none";
        }

        geotagged.forEach((r) => {
            const markerColor = r.severity === "HIGH" || r.priority_level === "HIGH" ? "#ef4444" : (r.severity === "MEDIUM" || r.priority_level === "MEDIUM" ? "#f59e0b" : "#10b981");

            const customCircleMarker = L.circleMarker([r.latitude, r.longitude], {
                radius: 10,
                fillColor: markerColor,
                color: "#ffffff",
                weight: 2,
                opacity: 1,
                fillOpacity: 0.85,
            });

            const popupHtml = `
                <div class="map-popup-card">
                    <h4>Report #${r.id} (${r.damage_type || "Road Damage"})</h4>
                    <p><strong>Severity:</strong> ${r.severity || "LOW"}</p>
                    <p><strong>Priority:</strong> ${r.priority_level || "LOW"} (${r.priority_score || 0})</p>
                    <p><strong>Status:</strong> ${r.status}</p>
                    <p><strong>Coordinates:</strong> ${r.latitude.toFixed(4)}, ${r.longitude.toFixed(4)}</p>
                    <button class="btn btn-emerald btn-popup" onclick="openReportModal(${r.id})">Inspect Full Details</button>
                </div>
            `;

            customCircleMarker.bindPopup(popupHtml);
            customCircleMarker.addTo(gisMapInstance);
            mapMarkersList.push(customCircleMarker);
        });

        if (mapMarkersList.length > 0) {
            const group = L.featureGroup(mapMarkersList);
            gisMapInstance.fitBounds(group.getBounds().pad(0.2));
        }
    } catch (err) {
        console.error("GIS Map refresh error:", err);
    }
}

/* ==========================================================================
   8. ANALYTICS SECTION (CHART.JS INTEGRATION)
   ========================================================================== */
function initAnalyticsSection() {
    loadAnalyticsData();
}

async function loadAnalyticsData() {
    const emptyNotice = document.getElementById("analytics-empty-state");
    const chartsGrid = document.getElementById("analytics-charts-grid");

    try {
        const res = await fetch(`${API_BASE_URL}/analytics`);
        if (!res.ok) return;

        const data = await res.json();

        if (!data.has_data || data.total_reports === 0) {
            if (emptyNotice) emptyNotice.style.display = "block";
            if (chartsGrid) chartsGrid.style.display = "none";
            return;
        }

        if (emptyNotice) emptyNotice.style.display = "none";
        if (chartsGrid) chartsGrid.style.display = "grid";

        renderAnalyticsCharts(data);
    } catch (err) {
        console.error("Error loading analytics data:", err);
    }
}

function renderAnalyticsCharts(data) {
    const chartDefaults = {
        color: "#94a3b8",
        borderColor: "#334155",
    };
    Chart.defaults.color = chartDefaults.color;

    // 1. Damage Type Chart
    const dtCtx = document.getElementById("chart-damage-type");
    if (dtCtx) {
        if (chartDamageType) chartDamageType.destroy();
        chartDamageType = new Chart(dtCtx, {
            type: "doughnut",
            data: {
                labels: Object.keys(data.by_damage_type),
                datasets: [{
                    data: Object.values(data.by_damage_type),
                    backgroundColor: ["#ef4444", "#f59e0b", "#3b82f6", "#8b5cf6", "#64748b", "#10b981"],
                }],
            },
            options: { responsive: true, maintainAspectRatio: false },
        });
    }

    // 2. Severity Level Chart
    const sevCtx = document.getElementById("chart-severity");
    if (sevCtx) {
        if (chartSeverity) chartSeverity.destroy();
        chartSeverity = new Chart(sevCtx, {
            type: "bar",
            data: {
                labels: Object.keys(data.by_severity),
                datasets: [{
                    label: "Reports Count",
                    data: Object.values(data.by_severity),
                    backgroundColor: ["#10b981", "#f59e0b", "#ef4444"],
                }],
            },
            options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } } },
        });
    }

    // 3. Priority Level Chart
    const priCtx = document.getElementById("chart-priority");
    if (priCtx) {
        if (chartPriority) chartPriority.destroy();
        chartPriority = new Chart(priCtx, {
            type: "bar",
            data: {
                labels: Object.keys(data.by_priority_level),
                datasets: [{
                    label: "Priority Levels",
                    data: Object.values(data.by_priority_level),
                    backgroundColor: ["#ef4444", "#f59e0b", "#10b981"],
                }],
            },
            options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } } },
        });
    }

    // 4. Status Tracking Chart
    const stCtx = document.getElementById("chart-status");
    if (stCtx) {
        if (chartStatus) chartStatus.destroy();
        chartStatus = new Chart(stCtx, {
            type: "doughnut",
            data: {
                labels: Object.keys(data.by_status),
                datasets: [{
                    data: Object.values(data.by_status),
                    backgroundColor: ["#3b82f6", "#8b5cf6", "#10b981"],
                }],
            },
            options: { responsive: true, maintainAspectRatio: false },
        });
    }

    // 5. Timeline Chart
    const timeCtx = document.getElementById("chart-timeline");
    if (timeCtx) {
        if (chartTimeline) chartTimeline.destroy();
        const dates = (data.reports_over_time || []).map((t) => t.date);
        const counts = (data.reports_over_time || []).map((t) => t.count);

        chartTimeline = new Chart(timeCtx, {
            type: "line",
            data: {
                labels: dates.length > 0 ? dates : ["Today"],
                datasets: [{
                    label: "Reports Ingested",
                    data: counts.length > 0 ? counts : [data.total_reports],
                    borderColor: "#3b82f6",
                    backgroundColor: "rgba(59, 130, 246, 0.2)",
                    fill: true,
                    tension: 0.3,
                }],
            },
            options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } } },
        });
    }
}

/* ==========================================================================
   9. REPORT DETAILS MODAL HANDLERS & STATUS UPDATES
   ========================================================================== */
function initModalHandlers() {
    const closeBtn = document.getElementById("modal-close-btn");
    const backdrop = document.getElementById("report-modal-backdrop");
    const saveStatusBtn = document.getElementById("modal-save-status-btn");
    const viewMapBtn = document.getElementById("modal-view-map-btn");
    const deleteBtn = document.getElementById("modal-delete-btn");

    if (closeBtn) closeBtn.addEventListener("click", closeModal);
    if (backdrop) {
        backdrop.addEventListener("click", (e) => {
            if (e.target === backdrop) closeModal();
        });
    }

    if (saveStatusBtn) {
        saveStatusBtn.addEventListener("click", async () => {
            if (!activeReportInModal) return;
            const newStatus = document.getElementById("modal-status-select").value;

            try {
                const res = await fetch(`${API_BASE_URL}/reports/${activeReportInModal.id}`, {
                    method: "PATCH",
                    headers: buildHeaders({ "Content-Type": "application/json" }),
                    body: JSON.stringify({ status: newStatus }),
                });

                if (!res.ok) throw new Error("Failed to update status.");

                const updated = await res.json();
                activeReportInModal = updated;
                showMsg("modal-status-msg", `✅ Workflow status updated to ${newStatus}!`, true);

                loadReportsTable();
                loadDashboardStats();
                refreshGISMap();
            } catch (err) {
                showMsg("modal-status-msg", `Error updating status: ${err.message}`, false);
            }
        });
    }

    if (viewMapBtn) {
        viewMapBtn.addEventListener("click", () => {
            if (!activeReportInModal || activeReportInModal.latitude === null || activeReportInModal.longitude === null) {
                alert("This report does not have GPS coordinates to plot on the map.");
                return;
            }

            closeModal();
            const mapTabBtn = document.getElementById("nav-map");
            if (mapTabBtn) mapTabBtn.click();

            setTimeout(() => {
                if (gisMapInstance) {
                    gisMapInstance.setView([activeReportInModal.latitude, activeReportInModal.longitude], 16);
                }
            }, 300);
        });
    }

    if (deleteBtn) {
        deleteBtn.addEventListener("click", async () => {
            if (!activeReportInModal) return;
            if (confirm(`Delete Report #${activeReportInModal.id} permanently?`)) {
                await deleteReportRecord(activeReportInModal.id);
                closeModal();
            }
        });
    }
}

async function openReportModal(reportId) {
    try {
        const res = await fetch(`${API_BASE_URL}/reports/${reportId}`);
        if (!res.ok) throw new Error("Report not found.");

        const report = await res.json();
        activeReportInModal = report;

        document.getElementById("modal-report-title").textContent = `Report Details #${report.id}`;
        document.getElementById("modal-damage-type").textContent = report.damage_type || "N/A";
        document.getElementById("modal-severity").innerHTML = getSeverityBadge(report.severity);
        document.getElementById("modal-confidence").textContent = report.confidence !== null ? `${(report.confidence * 100).toFixed(1)}%` : "N/A";
        document.getElementById("modal-priority-level").textContent = `${report.priority_level || "LOW"} (${report.priority_score || 0}/100)`;
        document.getElementById("modal-priority-reason").textContent = report.priority_reason || "Calculated priority rationale.";

        const locStr = (report.latitude !== null && report.longitude !== null)
            ? `📍 ${report.latitude.toFixed(6)}, ${report.longitude.toFixed(6)}`
            : "Location unavailable";
        document.getElementById("modal-location").textContent = locStr;

        document.getElementById("modal-timestamp").textContent = report.timestamp ? new Date(report.timestamp).toLocaleString() : "--";
        document.getElementById("modal-description").textContent = report.description || "None provided.";
        document.getElementById("modal-status-select").value = report.status || "NEW";

        // Images
        const origImg = document.getElementById("modal-img-original");
        const annotImg = document.getElementById("modal-img-annotated");
        origImg.src = report.image_path ? `${API_BASE_URL}/${report.image_path}` : "";
        annotImg.src = report.annotated_image_path ? `${API_BASE_URL}/${report.annotated_image_path}` : origImg.src;

        document.getElementById("modal-status-msg").style.display = "none";
        document.getElementById("report-modal-backdrop").style.display = "flex";
    } catch (err) {
        alert(`Error opening report modal: ${err.message}`);
    }
}

function closeModal() {
    const backdrop = document.getElementById("report-modal-backdrop");
    if (backdrop) backdrop.style.display = "none";
    activeReportInModal = null;
}

/* ==========================================================================
   10. HELPER FUNCTIONS & BADGE BUILDERS
   ========================================================================== */
function getSeverityBadge(sev) {
    if (!sev) return `<span class="badge">N/A</span>`;
    const cls = getSeverityBadgeClass(sev);
    return `<span class="badge ${cls}">${sev}</span>`;
}

function getSeverityBadgeClass(sev) {
    if (sev === "HIGH") return "badge-danger";
    if (sev === "MEDIUM") return "badge-warning";
    return "badge-success";
}

function getStatusBadge(st) {
    if (st === "NEW") return `<span class="badge badge-info">NEW</span>`;
    if (st === "REVIEWED") return `<span class="badge badge-purple">REVIEWED</span>`;
    if (st === "RESOLVED") return `<span class="badge badge-success">RESOLVED</span>`;
    return `<span class="badge">${st || "NEW"}</span>`;
}

function showMsg(elementId, text, isSuccess) {
    const el = document.getElementById(elementId);
    if (el) {
        el.className = `response-msg ${isSuccess ? "success" : "error"}`;
        el.textContent = text;
        el.style.display = "block";
    }
}
