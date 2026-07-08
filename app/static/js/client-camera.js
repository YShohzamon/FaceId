/**
 * Client-side camera helper for mobile browsers.
 * Uses getUserMedia so the phone's own camera is used when
 * accessing the local server over Wi-Fi.
 */
window.ClientCamera = (function () {
    let stream = null;
    let videoEl = null;
    let canvasEl = null;
    let facingMode = 'user';

    function _ensureMediaDevices() {
        if (!navigator.mediaDevices) {
            navigator.mediaDevices = {};
        }
        if (!navigator.mediaDevices.getUserMedia) {
            const legacy =
                navigator.getUserMedia ||
                navigator.webkitGetUserMedia ||
                navigator.mozGetUserMedia;
            if (legacy) {
                navigator.mediaDevices.getUserMedia = (constraints) =>
                    new Promise((resolve, reject) => {
                        legacy.call(navigator, constraints, resolve, reject);
                    });
            }
        }
    }

    function isSecureEnough() {
        return window.isSecureContext === true;
    }

    function getHttpsUrl() {
        const host = window.location.hostname;
        const port = window.location.port || '8000';
        return `https://${host}:${port}${window.location.pathname}${window.location.search}${window.location.hash}`;
    }

    function getBlockedReason() {
        if (isSecureEnough() && isSupported()) return null;

        const host = window.location.hostname;
        const httpsUrl = getHttpsUrl();

        if (!isSecureEnough() && isRemoteClient()) {
            return (
                'Phone camera requires HTTPS. ' +
                `Open ${httpsUrl} on your phone ` +
                '(accept the security warning), then try again.'
            );
        }

        if (!isSupported()) {
            return (
                'Camera API not available in this browser. ' +
                'Use Chrome on Android or Safari on iPhone with HTTPS.'
            );
        }

        return null;
    }

    function isSupported() {
        _ensureMediaDevices();
        return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
    }

    function isMobileDevice() {
        return /Android|iPhone|iPad|iPod|Mobile|webOS|BlackBerry|Opera Mini|IEMobile/i.test(
            navigator.userAgent
        );
    }

    function isTouchDevice() {
        return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
    }

    function isRemoteClient() {
        const host = window.location.hostname;
        return host !== 'localhost' && host !== '127.0.0.1' && host !== '';
    }

    function shouldUseClientCamera() {
        // Phone/tablet opening server via LAN IP → always use device camera
        if (isRemoteClient()) return true;
        if (isMobileDevice() || isTouchDevice()) return true;
        return false;
    }

    function stopTracks() {
        if (!stream) return;
        stream.getTracks().forEach((track) => track.stop());
        stream = null;
    }

    async function start(containerEl, options = {}) {
        _ensureMediaDevices();

        const blocked = getBlockedReason();
        if (blocked) {
            throw new Error(blocked);
        }

        facingMode = options.facingMode || 'user';

        if (!videoEl) {
            videoEl = document.createElement('video');
            videoEl.setAttribute('playsinline', '');
            videoEl.setAttribute('webkit-playsinline', '');
            videoEl.setAttribute('autoplay', '');
            videoEl.muted = true;
            videoEl.id = options.videoId || 'clientVideo';
            videoEl.style.cssText =
                'width:100%;height:100%;object-fit:cover;display:block;max-width:100%;';
        }

        if (!canvasEl) {
            canvasEl = document.createElement('canvas');
            canvasEl.style.display = 'none';
        }

        await _startStream();

        if (containerEl && !containerEl.contains(videoEl)) {
            containerEl.appendChild(videoEl);
        }

        return videoEl;
    }

    async function _startStream() {
        stopTracks();

        const constraints = {
            audio: false,
            video: {
                facingMode: { ideal: facingMode },
                width: { ideal: 1280, max: 1920 },
                height: { ideal: 720, max: 1080 },
            },
        };

        try {
            stream = await navigator.mediaDevices.getUserMedia(constraints);
        } catch (firstErr) {
            try {
                stream = await navigator.mediaDevices.getUserMedia({
                    audio: false,
                    video: {
                        facingMode: facingMode,
                    },
                });
            } catch (_) {
                try {
                    stream = await navigator.mediaDevices.getUserMedia({
                        audio: false,
                        video: true,
                    });
                } catch (finalErr) {
                    const msg = finalErr.name === 'NotAllowedError'
                        ? 'Camera permission denied. Allow camera access in browser settings.'
                        : finalErr.name === 'NotFoundError'
                            ? 'No camera found on this device.'
                            : 'Could not open camera: ' + (finalErr.message || 'unknown error');
                    throw new Error(msg);
                }
            }
        }

        videoEl.srcObject = stream;
        await videoEl.play();
    }

    async function stop() {
        stopTracks();
        if (videoEl) {
            videoEl.srcObject = null;
            if (videoEl.parentNode) {
                videoEl.parentNode.removeChild(videoEl);
            }
            videoEl = null;
        }
    }

    async function flip() {
        facingMode = facingMode === 'user' ? 'environment' : 'user';
        if (videoEl) {
            await _startStream();
        }
        return facingMode;
    }

    function getFacingLabel() {
        return facingMode === 'user' ? 'Front' : 'Back';
    }

    async function captureBlob(quality = 0.92) {
        if (!videoEl || !stream || videoEl.readyState < 2) {
            return null;
        }

        const width = videoEl.videoWidth;
        const height = videoEl.videoHeight;
        if (!width || !height) return null;

        canvasEl.width = width;
        canvasEl.height = height;
        const ctx = canvasEl.getContext('2d');
        ctx.drawImage(videoEl, 0, 0, width, height);

        return new Promise((resolve) => {
            canvasEl.toBlob((blob) => resolve(blob), 'image/jpeg', quality);
        });
    }

    function isRunning() {
        return !!(stream && stream.active);
    }

    return {
        isSupported,
        isSecureEnough,
        getBlockedReason,
        getHttpsUrl,
        isMobileDevice,
        isRemoteClient,
        shouldUseClientCamera,
        start,
        stop,
        flip,
        getFacingLabel,
        captureBlob,
        isRunning,
    };
})();
