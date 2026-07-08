/**
 * Student list page — delete confirmation modal.
 */

let pendingDeleteId = null;

function deleteStudent(id, name) {
    pendingDeleteId = id;
    document.getElementById('deleteStudentName').textContent = name;
    document.getElementById('deleteModal').style.display = 'flex';
}

function closeDeleteModal() {
    pendingDeleteId = null;
    document.getElementById('deleteModal').style.display = 'none';
}

const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');
if (confirmDeleteBtn) {
    confirmDeleteBtn.addEventListener('click', async () => {
        if (!pendingDeleteId) return;

        confirmDeleteBtn.disabled = true;
        confirmDeleteBtn.textContent = 'Deleting...';

        try {
            const response = await fetch(`/api/students/${pendingDeleteId}`, {
                method: 'DELETE',
            });

            if (response.ok) {
                closeDeleteModal();
                showToast('Student deleted successfully.', 'success');
                setTimeout(() => window.location.reload(), 800);
            } else {
                let msg = 'Could not delete student.';
                try { msg = (await response.json()).detail || msg; } catch (_) {}
                showToast('Error: ' + msg, 'error');
            }
        } catch (err) {
            showToast('Network error. Please try again.', 'error');
        } finally {
            confirmDeleteBtn.disabled = false;
            confirmDeleteBtn.textContent = 'Delete';
            closeDeleteModal();
        }
    });
}

document.getElementById('deleteModal')?.addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeDeleteModal();
});
