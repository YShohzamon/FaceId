/**
 * Recognition page — live MJPEG stream from server webcam + status polling.
 */

const startBtn           = document.getElementById('startBtn');
const stopBtn            = document.getElementById('stopBtn');
const videoFeed          = document.getElementById('videoFeed');
const placeholder        = document.getElementById('cameraPlaceholder');
const fpsValue           = document.getElementById('fpsValue');
const cameraStatus       = document.getElementById('cameraStatus');
const detectionStatus    = document.getElementById('detectionStatus');
const recognitionStatus  = document.getElementById('recognitionStatus');
const resultName         = document.getElementById('resultName');
const confidenceBar      = document.getElementById('confidenceBar');
const confidenceValue    = document.getElementById('confidenceValue');
const lastAttendanceText = document.getElementById('lastAttendanceText');

let statusPollInterval = null;

startBtn.addEventListener('click', async () => {
    startBtn.disabled = true;
    startBtn.innerHTML = 'Loading model...';

    try {
        await startServerCamera();
    } catch (err) {
        showError(err.message || 'Failed to start camera.');
        resetStartBtn();
    }
});

async function startServerCamera() {
    const res = await fetch('/api/stream/start', { method: 'POST' });
    let data = {};
    try { data = await res.json(); } catch (_) {
        showError(`Server error (HTTP ${res.status}). Check server logs.`);
        resetStartBtn();
        return;
    }

    if (!res.ok) {
        showError(data.detail || 'Failed to start camera.');
        resetStartBtn();
        return;
    }

    videoFeed.src = '/api/stream/feed';
    videoFeed.style.display = 'block';
    placeholder.style.display = 'none';

    startBtn.disabled = true;
    stopBtn.disabled = false;
    setCameraStatus(true);
    setDetectionStatus(data.embedder_ready ? 'active' : 'error');
    startStatusPolling();
    fetchLastAttendance();
}

stopBtn.addEventListener('click', async () => {
    stopBtn.disabled = true;

    try { await fetch('/api/stream/stop', { method: 'POST' }); } catch (_) {}
    videoFeed.src = '';
    videoFeed.style.display = 'none';

    placeholder.style.display = 'flex';
    startBtn.disabled = false;
    stopStatusPolling();
    setCameraStatus(false);
    setDetectionStatus('idle');
    setRecognitionStatus('idle');
    fpsValue.textContent = '-- FPS';
    setRecognitionResult('Waiting...', 0, 'idle');
    resetStartBtn();
});

function startStatusPolling() {
    statusPollInterval = setInterval(async () => {
        try {
            const res = await fetch('/api/stream/status');
            const data = await res.json();

            if (!data.running) {
                handleCameraStopped();
                return;
            }

            fpsValue.textContent = data.fps + ' FPS';
            setDetectionStatus(data.embedder_ready ? 'active' : 'error');
            applyRecognitionData(data);
        } catch (_) {}
    }, 500);
}

function stopStatusPolling() {
    if (statusPollInterval) {
        clearInterval(statusPollInterval);
        statusPollInterval = null;
    }
}

function applyRecognitionData(data) {
    if (data.face_detected) {
        if (data.state === 'known') {
            setRecognitionResult(data.label, data.confidence, 'known');
            setRecognitionStatus('known');
        } else if (data.state === 'unknown') {
            setRecognitionResult('Stranger', data.confidence, 'unknown');
            setRecognitionStatus('unknown');
        } else {
            setRecognitionResult('Scanning...', 0, 'scanning');
            setRecognitionStatus('scanning');
        }
    } else {
        setRecognitionResult('No face detected', 0, 'idle');
        setRecognitionStatus('idle');
    }

    if (data.attendance_logged) {
        showAttendanceLogged(data.label, data.confidence);
    } else if (data.state === 'known' && data.cooldown_remaining > 0) {
        showCooldown(data.label, data.cooldown_remaining);
    }
}

function handleCameraStopped() {
    stopStatusPolling();
    setCameraStatus(false);
    setDetectionStatus('idle');
    setRecognitionStatus('idle');
    videoFeed.src = '';
    videoFeed.style.display = 'none';
    placeholder.style.display = 'flex';
    startBtn.disabled = false;
    stopBtn.disabled = true;
    fpsValue.textContent = '-- FPS';
}

async function fetchLastAttendance() {
    try {
        const res = await fetch('/api/attendance/last');
        const data = await res.json();
        if (data.found) {
            lastAttendanceText.textContent =
                `${data.student_name} — ${data.attendance_date} ${data.attendance_time} ` +
                `(${Math.round(data.confidence * 100)}%)`;
        } else {
            lastAttendanceText.textContent = 'No records yet.';
        }
    } catch (_) {}
}

function showAttendanceLogged(name, confidence) {
    const pct = Math.round(confidence * 100);
    const now = new Date();
    const time = now.toLocaleTimeString('en-US', { hour12: false });
    lastAttendanceText.textContent = `✓ ${name} logged at ${time} (${pct}%)`;
    lastAttendanceText.style.color = 'var(--green)';
    setTimeout(() => {
        lastAttendanceText.style.color = '';
        fetchLastAttendance();
    }, 3000);
}

function showCooldown(name, seconds) {
    lastAttendanceText.textContent = `${name} — cooldown: ${seconds}s remaining`;
}

function setCameraStatus(online) {
    cameraStatus.textContent = online ? 'Online' : 'Offline';
    cameraStatus.className = online
        ? 'status-badge status-badge--on'
        : 'status-badge status-badge--off';
}

function setDetectionStatus(state) {
    const map = {
        active: { text: 'Active', cls: 'status-badge--on' },
        idle:   { text: 'Idle',   cls: 'status-badge--off' },
        error:  { text: 'Error',  cls: 'status-badge--off' },
    };
    const s = map[state] || map.idle;
    detectionStatus.textContent = s.text;
    detectionStatus.className = 'status-badge ' + s.cls;
}

function setRecognitionStatus(state) {
    if (!recognitionStatus) return;
    const map = {
        known:    { text: 'Recognized', cls: 'status-badge--on' },
        unknown:  { text: 'Stranger',   cls: 'status-badge--off' },
        scanning: { text: 'Scanning',   cls: 'status-badge--cpu' },
        idle:     { text: 'Idle',       cls: 'status-badge--off' },
    };
    const s = map[state] || map.idle;
    recognitionStatus.textContent = s.text;
    recognitionStatus.className = 'status-badge ' + s.cls;
}

function setRecognitionResult(name, confidence, state) {
    resultName.textContent = name;
    const pct = Math.round(confidence * 100);
    confidenceBar.style.width = pct + '%';
    confidenceValue.textContent = pct + '%';
    const colors = {
        known: '#22c55e', unknown: '#f97316', scanning: '#4f7cff', idle: '#525c7a',
    };
    confidenceBar.style.background = colors[state] || colors.idle;
}

function resetStartBtn() {
    startBtn.disabled = false;
    startBtn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="5,3 19,12 5,21"/>
        </svg> Start Camera`;
}

function showError(msg) {
    if (typeof showToast === 'function') {
        showToast(msg, 'error', 8000);
    } else {
        alert('Camera error: ' + msg);
    }
}
