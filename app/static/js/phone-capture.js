/**
 * Phone camera via file capture — works over HTTP (no HTTPS required).
 * Uses <input type="file" capture> which opens the native camera on mobile.
 */
window.PhoneCapture = (function () {
    let facingMode = 'environment';
    let fileInput = null;

    function isPhone() {
        return /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent)
            || (navigator.maxTouchPoints > 0 && window.innerWidth <= 1024);
    }

    function isRemote() {
        const host = window.location.hostname;
        return host && host !== 'localhost' && host !== '127.0.0.1';
    }

    /** Use native camera capture instead of getUserMedia (HTTP-safe on phones). */
    function needsFallback() {
        return isPhone() && isRemote();
    }

    function _ensureInput() {
        if (!fileInput) {
            fileInput = document.createElement('input');
            fileInput.type = 'file';
            fileInput.accept = 'image/*';
            fileInput.style.display = 'none';
            document.body.appendChild(fileInput);
        }
        fileInput.setAttribute('capture', facingMode);
    }

    function getFacingLabel() {
        return facingMode === 'user' ? 'Front' : 'Back';
    }

    function flip() {
        facingMode = facingMode === 'user' ? 'environment' : 'user';
        if (fileInput) {
            fileInput.setAttribute('capture', facingMode);
        }
        return facingMode;
    }

    function takePhoto() {
        _ensureInput();
        return new Promise((resolve, reject) => {
            fileInput.value = '';

            const onChange = () => {
                fileInput.removeEventListener('change', onChange);
                const file = fileInput.files && fileInput.files[0];
                if (!file) {
                    resolve(null);
                    return;
                }
                resolve(file);
            };

            fileInput.addEventListener('change', onChange);
            fileInput.click();
        });
    }

    function previewFile(container, file) {
        if (!container || !file) return;
        let img = container.querySelector('.capture-preview-img');
        if (!img) {
            img = document.createElement('img');
            img.className = 'capture-preview-img';
            img.style.cssText = 'width:100%;height:100%;object-fit:cover;display:block;';
            container.appendChild(img);
        }
        if (img._blobUrl) URL.revokeObjectURL(img._blobUrl);
        img._blobUrl = URL.createObjectURL(file);
        img.src = img._blobUrl;
    }

    return {
        needsFallback,
        isPhone,
        takePhoto,
        flip,
        getFacingLabel,
        previewFile,
    };
})();
