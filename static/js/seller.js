// Modal functions
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'block';
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
    }
}

// Close modal when clicking outside
window.onclick = function(event) {
    if (event.target.classList.contains('modal')) {
        event.target.style.display = 'none';
    }
}

// Edit Product function
function editProduct(id, name, description, originalPrice, price, quantity, imagePath, unitType) {
    // Set form action
    const form = document.getElementById('edit-product-form');
    form.action = `/seller/products/update/${id}`;
    
    // Fill form fields
    document.getElementById('edit-name').value = name;
    document.getElementById('edit-description').value = description || '';
    document.getElementById('edit-original_price').value = originalPrice && originalPrice !== 'null' ? originalPrice : '';
    document.getElementById('edit-price').value = price;
    document.getElementById('edit-quantity').value = quantity;
    document.getElementById('edit-unit_type').value = unitType || 'quantity';
    
    // Open modal
    openModal('edit-product-modal');
}

// Edit Banner function
function editBanner(id, title, description, isActive, imagePath) {
    // Set form action
    const form = document.getElementById('edit-banner-form');
    form.action = `/seller/banners/update/${id}`;
    
    // Fill form fields
    document.getElementById('edit-banner-title').value = title;
    document.getElementById('edit-banner-description').value = description || '';
    document.getElementById('edit-banner-active').checked = isActive;
    
    // Open modal
    openModal('edit-banner-modal');
}



