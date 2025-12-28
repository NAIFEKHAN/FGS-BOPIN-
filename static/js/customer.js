// Update cart count on page load
document.addEventListener('DOMContentLoaded', function() {
    updateCartCount();
    initSearchAndFilters();

    // Attach click handlers to Add to cart buttons (no inline JS)
    document.querySelectorAll('.btn-add-cart[data-product-id]').forEach(btn => {
        btn.addEventListener('click', () => {
            const id = parseInt(btn.getAttribute('data-product-id'), 10);
            if (!isNaN(id)) {
                addToCart(id);
            }
        });
    });
});

function updateCartCount() {
    fetch('/api/cart/count')
        .then(response => response.json())
        .then(data => {
            const cartCountElements = document.querySelectorAll('#cart-count');
            cartCountElements.forEach(el => {
                el.textContent = data.count || 0;
            });
        })
        .catch(() => {
            // If endpoint doesn't exist, try to get from session
            const cartCountElements = document.querySelectorAll('#cart-count');
            cartCountElements.forEach(el => {
                el.textContent = '0';
            });
        });
}

function addToCart(productId) {
    const quantityElement = document.getElementById('qty-' + productId);
    if (!quantityElement) return;
    
    // Handle both input and select elements
    let quantity;
    if (quantityElement.tagName === 'SELECT') {
        quantity = parseFloat(quantityElement.value) || 1;
    } else {
        quantity = parseFloat(quantityElement.value) || 1;
    }
    
    fetch('/api/cart/add', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            product_id: productId,
            quantity: quantity
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Show success message
            showNotification('Item added to cart!', 'success');
            updateCartCount();
            // Reset quantity input/select
            if (quantityElement.tagName === 'SELECT') {
                quantityElement.value = '1'; // Reset to 1kg (default option)
            } else {
                quantityElement.value = 1;
            }
        } else {
            showNotification(data.error || 'Failed to add item to cart', 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showNotification('An error occurred. Please try again.', 'error');
    });
}

function showNotification(message, type) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        background: ${type === 'success' ? '#28a745' : '#dc3545'};
        color: white;
        border-radius: 4px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        z-index: 1000;
        animation: slideIn 0.3s ease-out;
    `;
    
    document.body.appendChild(notification);
    
    // Remove after 3 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 300);
    }, 3000);
}

// Add CSS animation if not already in stylesheet
if (!document.getElementById('notification-styles')) {
    const style = document.createElement('style');
    style.id = 'notification-styles';
    style.textContent = `
        @keyframes slideIn {
            from {
                transform: translateX(100%);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }
        @keyframes slideOut {
            from {
                transform: translateX(0);
                opacity: 1;
            }
            to {
                transform: translateX(100%);
                opacity: 0;
            }
        }
    `;
    document.head.appendChild(style);
}

// Quantity stepper for product cards
function changeQuantity(productId, delta) {
    const input = document.getElementById('qty-' + productId);
    if (!input) return;
    const current = parseInt(input.value || '1', 10);
    const min = parseInt(input.min || '1', 10);
    const max = parseInt(input.max || '99', 10);
    let next = current + delta;
    if (next < min) next = min;
    if (next > max) next = max;
    input.value = next;
}

// Smooth scroll to products section
function scrollToProducts() {
    const section = document.getElementById('products');
    if (section) {
        section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

// Search + quick filter logic
function initSearchAndFilters() {
    const searchInput = document.getElementById('product-search');
    const headerSearchInput = document.getElementById('header-search-input');
    const chips = document.querySelectorAll('.category-tab');
    const cards = document.querySelectorAll('.product-card');

    if (!cards.length) return;

    const applyFilters = (syncInputs = false) => {
        // Get query from either search input
        const query1 = (searchInput?.value || '').toLowerCase().trim();
        const query2 = (headerSearchInput?.value || '').toLowerCase().trim();
        const query = query1 || query2;
        
        // Only sync inputs when explicitly requested (not during typing)
        if (syncInputs && searchInput && headerSearchInput) {
            if (query1 && !query2) {
                headerSearchInput.value = searchInput.value;
            } else if (query2 && !query1) {
                searchInput.value = headerSearchInput.value;
            }
        }
        
        const activeChip = document.querySelector('.category-tab.category-tab--active');
        const category = activeChip ? activeChip.getAttribute('data-category') : 'all';

        let visibleCount = 0;
        cards.forEach(card => {
            const name = (card.getAttribute('data-name') || '').toLowerCase();
            const desc = (card.getAttribute('data-description') || '').toLowerCase();

            let matchesSearch = true;
            if (query) {
                matchesSearch = name.includes(query) || desc.includes(query);
            }

            let matchesCategory = true;
            if (category && category !== 'all') {
                const text = name + ' ' + desc;
                const rules = getCategoryKeywords(category);
                matchesCategory = rules.some(word => text.includes(word));
            }

            if (matchesSearch && matchesCategory) {
                card.style.display = '';
                visibleCount++;
            } else {
                card.style.display = 'none';
            }
        });

        // Show message if no products match
        const productsSection = document.querySelector('.products-section');
        let noResultsMsg = document.getElementById('no-results-message');
        if (visibleCount === 0 && (query || (category && category !== 'all'))) {
            if (!noResultsMsg) {
                noResultsMsg = document.createElement('div');
                noResultsMsg.id = 'no-results-message';
                noResultsMsg.className = 'empty-state';
                noResultsMsg.innerHTML = '<h3>No products found</h3><p>Try adjusting your search or filter.</p>';
                if (productsSection) {
                    const productsGrid = document.querySelector('.products-grid');
                    if (productsGrid && productsGrid.parentNode) {
                        productsGrid.parentNode.insertBefore(noResultsMsg, productsGrid.nextSibling);
                    }
                }
            }
            noResultsMsg.style.display = 'block';
        } else if (noResultsMsg) {
            noResultsMsg.style.display = 'none';
        }
    };

    // Initial filter application
    applyFilters();

    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            // Don't prevent default - allow normal typing
            e.stopPropagation();
            // small debounce
            clearTimeout(searchInput._debounceTimer);
            searchInput._debounceTimer = setTimeout(() => {
                applyFilters(false); // Don't sync during typing
            }, 150);
        });
    }

    if (headerSearchInput) {
        headerSearchInput.addEventListener('input', (e) => {
            // Don't prevent default - allow normal typing
            e.stopPropagation();
            // small debounce
            clearTimeout(headerSearchInput._debounceTimer);
            headerSearchInput._debounceTimer = setTimeout(() => {
                applyFilters(false); // Don't sync during typing
            }, 150);
        });
        
        // Sync on blur (when user leaves the input)
        headerSearchInput.addEventListener('blur', () => {
            if (searchInput && headerSearchInput.value) {
                searchInput.value = headerSearchInput.value;
            }
        });
        
        // Scroll to products on Enter key
        headerSearchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                scrollToProducts();
                applyFilters(true); // Sync on Enter
            }
        });
    }

    chips.forEach(chip => {
        chip.addEventListener('click', () => {
            chips.forEach(c => c.classList.remove('category-tab--active'));
            chip.classList.add('category-tab--active');
            applyFilters();
        });
    });
}

function getCategoryKeywords(category) {
    const map = {
        dairy: ['milk', 'cheese', 'butter', 'yogurt', 'curd', 'paneer', 'ghee', 'eggs', 'breads'],
        atta: ['atta', 'oil', 'dal', 'pulao', 'biriyani',  'sunflower', 'groundnut', 'mustard', 'olive', 'cooking oil'],
        rice: ['rice', 'basmati', 'sona', 'idli rice', 'pulao', 'biriyani'],
        masala: ['masala', 'dry fruits'],
        snacks: ['chips', 'snack', 'biscuit', 'cookie', 'namkeen', 'chocolate', 'nuts'],
        packaged: ['packaged', 'sugar'],
        juices: ['cold drinks', 'juices'],
        baby: ['baby care'],
        homeneeds: ['home needs', 'juices'],
        biscuits: ['biscuits', 'cookies', 'snacks']
    };
    return map[category] || [];
}
