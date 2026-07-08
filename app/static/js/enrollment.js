/**
 * Enrollment page — multi-angle face capture.
 *
 * Flow:
 *  1. User fills in name (+ optional student code)
 *  2. Clicks "Open Camera" OR "Add from File"
 *  3. For each of 5 angles:
 *       a. Show instruction
 *       b. Capture from camera OR upload an image file
 *       c. POST /api/enroll/capture/{studentId}/{angleIndex}
 *          or POST /api/enroll/upload/{studentId}/{angleIndex}
 *       d. On success → dot turns green, move to next angle
 *  4. After all 5 → generate embeddings → enable Save button
 */

// --- DOM refs ---
const studentNameInput       = document.getElementById('studentName');
const studentCodeInput       = document.getElementById('studentCode');
const openCameraBtn          = document.getElementById('openCameraBtn');
const uploadFromFileBtn      = document.getElementById('uploadFromFileBtn');
const faceFileInput          = document.getElementById('faceFileInput');
const capturePreview         = document.getElementById('captureCameraBox');
const previewPlaceholder     = document.getElementById('capturePreviewPlaceholder');
const capturePlaceholderText = document.getElementById('capturePlaceholderText');
const angleOverlay           = document.getElementById('angleOverlay');
const angleLabel             = document.getElementById('angleLabel');
const angleProgress          = document.getElementById('angleProgress');
const captureStatus          = document.getElementById('captureStatus');
const saveBtn                = document.getElementById('saveBtn');
const enrollForm             = document.getElementById('enrollForm');
const successAlert             = document.getElementById('successAlert');
const successMessage         = document.getElementById('successMessage');
const errorAlert             = document.getElementById('errorAlert');
const errorMessage           = document.getElementById('errorMessage');

// --- State ---
let studentId       = null;
let currentAngle    = 0;
let totalAngles     = 5;
let angles          = [];
let cameraStarted   = false;
let enrollmentMode  = null; // 'camera' | 'file'
let flipCameraBtn   = null;
let captureBtn      = null;
let uploadBtn       = null;
let isUploading     = false;

const ANGLE_INSTRUCTIONS = [
    "Look straight at the camera",
    "Turn head slightly LEFT",
    "Turn head slightly RIGHT",
    "Tilt head slightly UP",
    "Tilt head slightly DOWN",
];

const CAMERA_ICON = `
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="2" y="3" width="20" height="14" rx="2"/>
        <circle cx="12" cy="10" r="3"/>
    </svg>`;

const UPLOAD_ICON = `
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
        <polyline points="17,8 12,3 7,8"/>
        <line x1="12" y1="3" x2="12" y2="15"/>
    </svg>`;

const CAPTURE_ICON = `
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="3"/>
        <path d="M20.94 11A9 9 0 0 0 3.06 11"/>
        <path d="M3.06 13A9 9 0 0 0 20.94 13"/>
    </svg>`;

// ------------------------------------------------------------------
// Step 1: Start enrollment
// ------------------------------------------------------------------
openCameraBtn.addEventListener('click', () => startEnrollment('camera'));
uploadFromFileBtn.addEventListener('click', () => startEnrollment('file'));

faceFileInput.addEventListener('change', async () => {
    if (!faceFileInput.files.length || isUploading) return;
    await handleFileUpload(faceFileInput.files[0]);
    faceFileInput.value = '';
});

async function startEnrollment(mode) {
    const name = studentNameInput.value.trim();
    if (!name) {
        showError('Please enter the student name first.');
        studentNameInput.focus();
        return;
    }

    enrollmentMode = mode;
    hideAlerts();
    setStartButtonsDisabled(true);

    const startLabel = mode === 'camera' ? 'Starting camera...' : 'Preparing upload...';
    if (mode === 'camera') {
        openCameraBtn.innerHTML = startLabel;
    } else {
        uploadFromFileBtn.innerHTML = startLabel;
    }

    try {
        if (mode === 'camera') {
            const camRes = await fetch('/api/stream/start', { method: 'POST' });
            let camData = {};
            try { camData = await camRes.json(); } catch (_) {}
            if (!camRes.ok) {
                showError(camData.detail || 'Failed to start camera.');
                resetStartButtons();
                return;
            }
        }

        const stuRes = await fetch('/api/enroll/student', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                student_code: studentCodeInput.value.trim() || null,
            }),
        });
        const stuData = await stuRes.json();
        if (!stuRes.ok) {
            showError(stuData.detail || 'Failed to create student.');
            if (mode === 'camera') {
                fetch('/api/stream/stop', { method: 'POST' }).catch(() => {});
            }
            resetStartButtons();
            return;
        }

        studentId = stuData.student_id;

        const angRes = await fetch('/api/enroll/angles');
        const angData = await angRes.json();
        angles = angData.angles;
        totalAngles = angles.length;

        studentNameInput.disabled = true;
        studentCodeInput.disabled = true;
        openCameraBtn.style.display = 'none';
        uploadFromFileBtn.style.display = 'none';

        if (mode === 'camera') {
            enrollmentMode = 'camera';
            showCameraFeed();
            cameraStarted = true;
        } else {
            showFileUploadPreview();
        }

        startCaptureWorkflow();
    } catch (err) {
        showError('Network error: ' + err.message);
        if (mode === 'camera') {
            fetch('/api/stream/stop', { method: 'POST' }).catch(() => {});
        }
        resetStartButtons();
    }
}

// ------------------------------------------------------------------
// Capture workflow
// ------------------------------------------------------------------
function startCaptureWorkflow() {
    showAngle(currentAngle);
    insertCaptureControls();
}

function showAngle(index) {
    angleOverlay.style.display = 'flex';
    angleLabel.textContent = ANGLE_INSTRUCTIONS[index];
    angleProgress.textContent = `${index + 1} / ${totalAngles}`;
    updateDot(index, 'active');

    if (enrollmentMode === 'file') {
        setCaptureStatus(`Upload image ${index + 1}: "${ANGLE_INSTRUCTIONS[index]}"`);
    } else {
        setCaptureStatus(`Ready to capture angle ${index + 1}: "${ANGLE_INSTRUCTIONS[index]}"`);
    }
}

function insertCaptureControls() {
    const controls = document.querySelector('.capture-controls');
    controls.innerHTML = '';

    if (enrollmentMode === 'file') {
        uploadBtn = document.createElement('button');
        uploadBtn.type = 'button';
        uploadBtn.className = 'btn btn--primary';
        uploadBtn.id = 'uploadBtn';
        uploadBtn.innerHTML = `${UPLOAD_ICON} Choose Image`;
        uploadBtn.addEventListener('click', () => faceFileInput.click());
        controls.appendChild(uploadBtn);
        return;
    }

    captureBtn = document.createElement('button');
    captureBtn.type = 'button';
    captureBtn.className = 'btn btn--primary';
    captureBtn.id = 'captureBtn';
    captureBtn.innerHTML = `${CAPTURE_ICON} Capture`;
    captureBtn.addEventListener('click', handleCapture);
    controls.appendChild(captureBtn);

    uploadBtn = document.createElement('button');
    uploadBtn.type = 'button';
    uploadBtn.className = 'btn btn--secondary';
    uploadBtn.id = 'uploadBtn';
    uploadBtn.innerHTML = `${UPLOAD_ICON} Upload File`;
    uploadBtn.addEventListener('click', () => faceFileInput.click());
    controls.appendChild(uploadBtn);
}

async function handleCapture() {
    captureBtn.disabled = true;
    if (uploadBtn) uploadBtn.disabled = true;
    if (flipCameraBtn) flipCameraBtn.disabled = true;
    captureBtn.innerHTML = 'Capturing...';
    hideAlerts();

    try {
        const res = await fetch(`/api/enroll/capture/${studentId}/${currentAngle}`, {
            method: 'POST',
        });
        await handleAngleResponse(res, 'capture');
    } catch (err) {
        showError('Network error: ' + err.message);
        resetAngleButtons();
    }
}

async function handleFileUpload(file) {
    if (!studentId) return;

    isUploading = true;
    if (uploadBtn) {
        uploadBtn.disabled = true;
        uploadBtn.innerHTML = 'Uploading...';
    }
    if (captureBtn) captureBtn.disabled = true;
    hideAlerts();

    showSelectedFilePreview(file);

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch(`/api/enroll/upload/${studentId}/${currentAngle}`, {
            method: 'POST',
            body: formData,
        });
        await handleAngleResponse(res, 'upload');
    } catch (err) {
        showError('Network error: ' + err.message);
        resetAngleButtons();
    } finally {
        isUploading = false;
    }
}

async function handleAngleResponse(res, source) {
    let data = {};
    try { data = await res.json(); } catch (_) {}

    if (!res.ok) {
        showError(data.detail || (source === 'upload' ? 'Upload failed. Try another image.' : 'Capture failed. Try again.'));
        resetAngleButtons();
        return;
    }

    updateDot(currentAngle, 'done');
    currentAngle++;

    if (data.enrollment_complete) {
        onEnrollmentComplete(data);
    } else {
        showAngle(currentAngle);
        resetAngleButtons();
        const action = source === 'upload' ? 'uploaded' : 'captured';
        setCaptureStatus(`✓ Angle ${data.angles_done}/${totalAngles} ${action}. Now: "${ANGLE_INSTRUCTIONS[currentAngle]}"`);
    }
}

async function onEnrollmentComplete(data) {
    angleOverlay.style.display = 'none';
    for (let i = 0; i < totalAngles; i++) updateDot(i, 'done');

    if (cameraStarted) {
        fetch('/api/stream/stop', { method: 'POST' }).catch(() => {});
        cameraStarted = false;
    }

    const controls = document.querySelector('.capture-controls');
    controls.innerHTML = '';

    setCaptureStatus('Generating face embeddings (ArcFace)... Please wait.');
    showSuccess('All 5 angles collected! Generating embeddings...');

    try {
        const genRes = await fetch(`/api/enroll/generate/${studentId}`, {
            method: 'POST',
        });
        let genData = {};
        try { genData = await genRes.json(); } catch (_) {}

        if (genRes.ok && genData.generated > 0) {
            setCaptureStatus(`Done! ${genData.generated} embeddings generated.`);
            showSuccess(
                `Student registered successfully! ` +
                `${genData.generated} face embeddings created. ` +
                `Click "Save & Finish" to continue.`
            );
        } else if (genRes.ok) {
            setCaptureStatus('Embeddings ready.');
            showSuccess('Student registered. Click "Save & Finish" to continue.');
        } else {
            setCaptureStatus('Embedding generation failed — student saved without embeddings.');
            showError(
                (genData.detail || 'Embedding generation error.') +
                ' You can re-enroll this student later.'
            );
        }
    } catch (err) {
        setCaptureStatus('Network error during embedding generation.');
        showError('Could not generate embeddings: ' + err.message);
    }

    saveBtn.disabled = false;
    saveBtn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="20,6 9,17 4,12"/>
        </svg>
        Save & Finish`;
}

// ------------------------------------------------------------------
// Form submit (Save button)
// ------------------------------------------------------------------
enrollForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!studentId) return;
    window.location.href = '/students';
});

// ------------------------------------------------------------------
// Preview helpers
// ------------------------------------------------------------------
function showCameraFeed() {
    previewPlaceholder.style.display = 'none';
    removePreviewImage();

    let img = document.getElementById('enrollFeed');
    if (!img) {
        img = document.createElement('img');
        img.id = 'enrollFeed';
        img.style.cssText = 'width:100%;height:100%;object-fit:cover;display:block;';
        capturePreview.appendChild(img);
    }
    img.src = '/api/stream/feed';
}

function showFileUploadPreview() {
    previewPlaceholder.style.display = 'flex';
    capturePlaceholderText.textContent = 'Choose an image file for each angle';
    removePreviewImage();
}

function showSelectedFilePreview(file) {
    previewPlaceholder.style.display = 'none';
    removePreviewImage('enrollFeed');

    let img = document.getElementById('filePreview');
    if (!img) {
        img = document.createElement('img');
        img.id = 'filePreview';
        img.style.cssText = 'width:100%;height:100%;object-fit:cover;display:block;';
        capturePreview.appendChild(img);
    }
    img.src = URL.createObjectURL(file);
}

function removePreviewImage(idToKeep) {
    ['enrollFeed', 'filePreview', 'enrollClientVideo', 'clientVideo'].forEach((id) => {
        if (id === idToKeep) return;
        const img = document.getElementById(id);
        if (img) {
            if (id === 'filePreview' && img.src.startsWith('blob:')) {
                URL.revokeObjectURL(img.src);
            }
            img.remove();
        }
    });
}

// ------------------------------------------------------------------
// Dot progress helpers
// ------------------------------------------------------------------
function updateDot(index, state) {
    const dot = document.getElementById(`dot-${index}`);
    if (!dot) return;
    dot.className = 'capture-dot';
    if (state === 'done')   dot.classList.add('done');
    if (state === 'active') dot.classList.add('active');
}

// ------------------------------------------------------------------
// Status / alert helpers
// ------------------------------------------------------------------
function setCaptureStatus(msg) {
    captureStatus.textContent = msg;
}

function showSuccess(msg) {
    successMessage.textContent = msg;
    successAlert.style.display = 'flex';
    errorAlert.style.display   = 'none';
}

function showError(msg) {
    errorMessage.textContent = msg;
    errorAlert.style.display   = 'flex';
    successAlert.style.display = 'none';
}

function hideAlerts() {
    successAlert.style.display = 'none';
    errorAlert.style.display   = 'none';
}

function setStartButtonsDisabled(disabled) {
    openCameraBtn.disabled = disabled;
    uploadFromFileBtn.disabled = disabled;
}

function resetStartButtons() {
    enrollmentMode = null;
    flipCameraBtn = null;
    setStartButtonsDisabled(false);
    openCameraBtn.style.display = '';
    uploadFromFileBtn.style.display = '';
    openCameraBtn.innerHTML = `${CAMERA_ICON} Open Camera`;
    uploadFromFileBtn.innerHTML = `${UPLOAD_ICON} Add from File`;
}

function resetAngleButtons() {
    if (captureBtn) {
        captureBtn.disabled = false;
        captureBtn.innerHTML = `${CAPTURE_ICON} Capture`;
    }
    if (flipCameraBtn) {
        flipCameraBtn.disabled = false;
    }
    if (uploadBtn) {
        uploadBtn.disabled = false;
        uploadBtn.innerHTML = enrollmentMode === 'file'
            ? `${UPLOAD_ICON} Choose Image`
            : `${UPLOAD_ICON} Upload File`;
    }
}
