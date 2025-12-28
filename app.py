from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file, flash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from io import BytesIO

from config import Config
from models import db, Product, OfferBanner, Order, OrderItem, Seller, PickupTimeSlot

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

# Ensure upload directories exist
PRODUCT_UPLOAD_DIR = os.path.join('static', 'uploads', 'products')
BANNER_UPLOAD_DIR = os.path.join('static', 'uploads', 'banners')
os.makedirs(PRODUCT_UPLOAD_DIR, exist_ok=True)
os.makedirs(BANNER_UPLOAD_DIR, exist_ok=True)

def send_order_email(order):
    """Send a simple order notification email to the seller, if email is configured."""
    from email.message import EmailMessage
    import smtplib

    seller_email = app.config.get('SELLER_EMAIL')
    mail_server = app.config.get('MAIL_SERVER')
    mail_port = app.config.get('MAIL_PORT', 587)
    mail_username = app.config.get('MAIL_USERNAME')
    mail_password = app.config.get('MAIL_PASSWORD')

    if not (seller_email and mail_server and mail_username and mail_password):
        # Email not configured; skip silently
        return

    msg = EmailMessage()
    msg['Subject'] = f"New BOPIS Order #{order.id}"
    msg['From'] = mail_username
    msg['To'] = seller_email

    lines = [
        f"New order placed (ID: {order.id})",
        "",
        f"Customer: {order.customer_name}",
        f"Email: {order.customer_email or 'N/A'}",
        f"Phone: {order.customer_phone}",
        f"Pickup time: {order.pickup_time.strftime('%Y-%m-%d %I:%M %p')}",
        "",
        "Items:"
    ]
    for item in order.items:
        lines.append(f"- {item.product.name} x {item.quantity} @ ${item.price:.2f}")
    lines.append("")
    lines.append(f"Total amount: ${order.total_amount:.2f}")

    msg.set_content("\n".join(lines))

    try:
        with smtplib.SMTP(mail_server, mail_port) as server:
            server.starttls()
            server.login(mail_username, mail_password)
            server.send_message(msg)
    except Exception as exc:
        # Log to console; avoid breaking checkout flow
        print(f"Error sending order email: {exc}")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def migrate_db():
    """Add missing columns to existing database and handle schema changes"""
    with app.app_context():
        try:
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            
            # Migrate products table
            try:
                columns = [col['name'] for col in inspector.get_columns('products')]
                
                if 'original_price' not in columns:
                    # Add the original_price column
                    db.session.execute(db.text("ALTER TABLE products ADD COLUMN original_price REAL"))
                    db.session.commit()
                    print("✓ Added original_price column to products table")
                
                if 'unit_type' not in columns:
                    # Add the unit_type column
                    db.session.execute(db.text("ALTER TABLE products ADD COLUMN unit_type TEXT DEFAULT 'quantity'"))
                    db.session.commit()
                    print("✓ Added unit_type column to products table")
                
                # Update existing products that might have null or incorrect unit_type
                # Check if any products have null unit_type or need updating
                products = Product.query.filter(
                    (Product.unit_type == None) | (Product.unit_type == '')
                ).all()
                if products:
                    for product in products:
                        # Set default to 'quantity' if null
                        product.unit_type = 'quantity'
                    db.session.commit()
                    print(f"✓ Updated {len(products)} products with default unit_type")
                
                # Auto-detect kg products based on name patterns
                kg_keywords = ['kg', 'kilogram', 'gram', 'g ', 'weight']
                products_to_update = Product.query.filter(
                    Product.unit_type == 'quantity'
                ).all()
                updated_count = 0
                for product in products_to_update:
                    name_lower = (product.name or '').lower()
                    if any(keyword in name_lower for keyword in kg_keywords):
                        product.unit_type = 'kg'
                        updated_count += 1
                if updated_count > 0:
                    db.session.commit()
                    print(f"✓ Auto-updated {updated_count} products to 'kg' unit_type based on name")
            except Exception as e:
                print(f"Products migration note: {e}")
            
            # Migrate orders table - make customer_email nullable
            try:
                if 'orders' in inspector.get_table_names():
                    # Check the table schema to see if we need to migrate
                    schema_info = db.session.execute(db.text(
                        "SELECT sql FROM sqlite_master WHERE type='table' AND name='orders'"
                    )).fetchone()
                    if schema_info and schema_info[0]:
                        schema_sql = schema_info[0]
                        # Normalize schema for checking (remove whitespace)
                        schema_normalized = schema_sql.replace(' ', '').replace('\n', '').replace('\t', '')
                        # Check if customer_email has NOT NULL constraint
                        if 'customer_emailVARCHAR(200)NOTNULL' in schema_normalized or \
                           'customer_emailVARCHAR(200)NOT' in schema_normalized:
                            # Need to recreate table with nullable customer_email
                            print("Migrating orders table to make customer_email nullable...")
                            
                            # Disable foreign key checks temporarily
                            db.session.execute(db.text("PRAGMA foreign_keys=OFF"))
                            
                            # Create new table with nullable customer_email
                            db.session.execute(db.text("""
                                CREATE TABLE orders_new (
                                    id INTEGER PRIMARY KEY,
                                    customer_name VARCHAR(200) NOT NULL,
                                    customer_email VARCHAR(200),
                                    customer_phone VARCHAR(20) NOT NULL,
                                    pickup_time DATETIME NOT NULL,
                                    total_amount FLOAT NOT NULL,
                                    status VARCHAR(50),
                                    created_at DATETIME
                                )
                            """))
                            
                            # Copy data from old table to new table
                            db.session.execute(db.text("""
                                INSERT INTO orders_new 
                                (id, customer_name, customer_email, customer_phone, pickup_time, total_amount, status, created_at)
                                SELECT id, customer_name, customer_email, customer_phone, pickup_time, total_amount, status, created_at
                                FROM orders
                            """))
                            
                            # Drop old table
                            db.session.execute(db.text("DROP TABLE orders"))
                            
                            # Rename new table
                            db.session.execute(db.text("ALTER TABLE orders_new RENAME TO orders"))
                            
                            # Re-enable foreign key checks
                            db.session.execute(db.text("PRAGMA foreign_keys=ON"))
                            
                            db.session.commit()
                            print("✓ Updated orders table: customer_email is now nullable")
            except Exception as e:
                # If the table structure is already correct or migration fails, rollback
                error_msg = str(e).lower()
                if "already exists" not in error_msg and "no such table" not in error_msg:
                    print(f"Orders migration note: {e}")
                try:
                    db.session.rollback()
                except:
                    pass
        except Exception as e:
            print(f"Migration note: {e}")
            # If migration fails, db.create_all() will handle it for new databases

def sync_time_slots():
    """Sync pickup time slots with desired slots"""
    desired_time_slots = [
        '7:00 AM', '8:00 AM', '9:00 AM', '10:00 AM', '11:00 AM', '12:00 PM',
        '1:00 PM', '4:00 PM', '5:00 PM', '6:00 PM', '7:00 PM', '8:00 PM'
    ]
    
    # Get all existing time slots
    existing_slots = PickupTimeSlot.query.all()
    existing_slot_values = {slot.time_slot for slot in existing_slots}
    desired_slot_set = set(desired_time_slots)
    
    # Remove time slots that are not in the desired list
    for slot in existing_slots:
        if slot.time_slot not in desired_slot_set:
            db.session.delete(slot)
    
    # Add new time slots that don't exist
    for slot_value in desired_time_slots:
        if slot_value not in existing_slot_values:
            pickup_slot = PickupTimeSlot(time_slot=slot_value, is_available=True)
            db.session.add(pickup_slot)
    # Ensure all desired slots are available
    for slot_value in desired_time_slots:
        slot = PickupTimeSlot.query.filter_by(time_slot=slot_value).first()
        if slot:
            slot.is_available = True
    
    db.session.commit()
def init_db():
    """Initialize database and create default data"""
    with app.app_context():
        # Run migration first to add any missing columns
        migrate_db()
        db.create_all()
        
        # Create default seller if not exists
        if not Seller.query.first():
            seller = Seller(username='admin')
            seller.set_password('admin123')
            db.session.add(seller)
        
        # Sync pickup time slots
        sync_time_slots()
        # Create some sample products if none exist (for demo/reference)
        if not Product.query.first():
            sample_products = [
                {
                    'name': 'Fresh Apples',
                    'description': 'Crisp and juicy red apples, perfect for snacking.',
                    'price': 120.0,
                    'original_price': 150.0,
                    'quantity': 40.0,
                    'unit_type': 'kg',
                    'image': 'uploads/products/apples.svg'
                },
                {
                    'name': 'Organic Bananas',
                    'description': 'Sweet organic bananas, naturally ripened.',
                    'price': 60.0,
                    'original_price': 75.0,
                    'quantity': 35.0,
                    'unit_type': 'dozen',
                    'image': 'uploads/products/bananas.svg'
                },
                {
                    'name': 'Whole Wheat Bread',
                    'description': 'Soft and healthy whole wheat bread loaf.',
                    'price': 45.0,
                    'original_price': 55.0,
                    'quantity': 25.0,
                    'unit_type': 'quantity',
                    'image': 'uploads/products/bread.svg'
                },
                {
                    'name': 'Fresh Milk',
                    'description': 'Pure and fresh toned milk in 1 litre pack.',
                    'price': 55.0,
                    'original_price': 65.0,
                    'quantity': 50.0,
                    'unit_type': 'litre',
                    'image': 'uploads/products/milk.svg'
                },
                {
                    'name': 'Brown Eggs',
                    'description': 'Farm fresh brown eggs, high in protein.',
                    'price': 70.0,
                    'original_price': 85.0,
                    'quantity': 30.0,
                    'unit_type': 'quantity',
                    'image': 'uploads/products/eggs.svg'
                }
            ]
            for p in sample_products:
                db.session.add(Product(
                    name=p['name'],
                    description=p['description'],
                    price=p['price'],
                    original_price=p.get('original_price'),
                    quantity_available=p['quantity'],
                    unit_type=p.get('unit_type', 'quantity'),
                    image_path=p.get('image')
                ))
        
        db.session.commit()

# Customer Routes
@app.route('/')
def index():
    products = Product.query.all()
    banners = OfferBanner.query.filter_by(is_active=True).all()
    return render_template('customer/index.html', products=products, banners=banners)

@app.route('/api/products')
def api_products():
    products = Product.query.all()
    result = []
    for p in products:
        d = p.to_dict()
        d['original_price'] = p.original_price  # Include original_price in API response
        result.append(d)
    return jsonify(result)

@app.route('/api/banners')
def api_banners():
    banners = OfferBanner.query.filter_by(is_active=True).all()
    return jsonify([b.to_dict() for b in banners])

@app.route('/api/cart/add', methods=['POST'])
def add_to_cart():
    data = request.json
    product_id = data.get('product_id')
    quantity = float(data.get('quantity', 1))
    
    product = Product.query.get_or_404(product_id)
    
    if quantity > product.quantity_available:
        return jsonify({'error': 'Insufficient stock'}), 400
    
    if 'cart' not in session:
        session['cart'] = []
    
    # Check if item already in cart
    cart = session['cart']
    item_found = False
    for item in cart:
        if item['product_id'] == product_id:
            new_quantity = item['quantity'] + quantity
            if new_quantity > product.quantity_available:
                return jsonify({'error': 'Insufficient stock'}), 400
            item['quantity'] = new_quantity
            item_found = True
            break
    
    if not item_found:
        cart.append({
            'product_id': product_id,
            'quantity': quantity,
            'price': product.price,
            'name': product.name,
            'image_path': product.image_path,
            'unit_type': product.unit_type
        })
    
    session['cart'] = cart
    session.modified = True
    return jsonify({'success': True, 'cart_count': len(cart)})

@app.route('/cart')
def cart():
    cart_items = []
    if 'cart' in session:
        for item in session['cart']:
            product = Product.query.get(item['product_id'])
            if product:
                cart_items.append({
                    'product_id': product.id,
                    'name': product.name,
                    'price': item['price'],
                    'quantity': item['quantity'],
                    'image_path': product.image_path,
                    'subtotal': item['price'] * item['quantity'],
                    'max_quantity': product.quantity_available,
                    'unit_type': product.unit_type
                })
    banners = OfferBanner.query.filter_by(is_active=True).all()
    return render_template('customer/cart.html', cart_items=cart_items, banners=banners)

@app.route('/api/cart/update', methods=['POST'])
def update_cart():
    data = request.json
    product_id = data.get('product_id')
    quantity = float(data.get('quantity', 0))
    
    if 'cart' not in session:
        return jsonify({'error': 'Cart is empty'}), 400
    
    product = Product.query.get_or_404(product_id)
    
    if quantity > product.quantity_available:
        return jsonify({'error': 'Insufficient stock'}), 400
    
    cart = session['cart']
    for item in cart:
        if item['product_id'] == product_id:
            if quantity == 0:
                cart.remove(item)
            else:
                item['quantity'] = quantity
            break
    
    session['cart'] = cart
    session.modified = True
    return jsonify({'success': True})

@app.route('/api/cart/remove', methods=['POST'])
def remove_from_cart():
    data = request.json
    product_id = data.get('product_id')
    
    if 'cart' not in session:
        return jsonify({'error': 'Cart is empty'}), 400
    
    cart = session['cart']
    cart[:] = [item for item in cart if item['product_id'] != product_id]
    
    session['cart'] = cart
    session.modified = True
    return jsonify({'success': True})

@app.route('/api/cart/count')
def cart_count():
    count = len(session.get('cart', []))
    return jsonify({'count': count})
def sort_time_slots(time_slots):
    """Sort time slots in chronological order"""
    def time_to_minutes(time_str):
        """Convert time string like '7:00 AM' to minutes since midnight"""
        try:
            time_obj = datetime.strptime(time_str, "%I:%M %p")
            return time_obj.hour * 60 + time_obj.minute
        except:
            return 0
    
    return sorted(time_slots, key=lambda slot: time_to_minutes(slot.time_slot))
@app.route('/checkout')
def checkout():
    if 'cart' not in session or not session['cart']:
        flash('Your cart is empty', 'warning')
        return redirect(url_for('cart'))
    
    # Get available time slots, ordered by time
        # Get available time slots and sort them chronologically
    time_slots = PickupTimeSlot.query.filter_by(is_available=True).all()
    time_slots = sort_time_slots(time_slots)
    banners = OfferBanner.query.filter_by(is_active=True).all()
    
    # Get next available date (today or tomorrow)
    today = datetime.now().date()
    tomorrow = today + timedelta(days=0)
    
    return render_template('customer/checkout.html', time_slots=time_slots, 
                         default_date=tomorrow.strftime('%Y-%m-%d'), banners=banners)

@app.route('/checkout', methods=['POST'])
def process_checkout():
    if 'cart' not in session or not session['cart']:
        return redirect(url_for('cart'))
    
    customer_name = request.form.get('customer_name')
    customer_email = request.form.get('customer_email') or None
    customer_phone = request.form.get('customer_phone')
    pickup_date = request.form.get('pickup_date')
    pickup_time_slot = request.form.get('pickup_time_slot')
    
    if not all([customer_name, customer_phone, pickup_date, pickup_time_slot]):
        flash('Please fill all required fields', 'error')
        return redirect(url_for('checkout'))
    
    # Parse pickup datetime
    try:
        pickup_datetime = datetime.strptime(f"{pickup_date} {pickup_time_slot}", "%Y-%m-%d %I:%M %p")
    except:
        flash('Invalid pickup time', 'error')
        return redirect(url_for('checkout'))
    
    # Validate stock and calculate total
    total = 0
    cart_items = []
    for item in session['cart']:
        product = Product.query.get(item['product_id'])
        if not product or product.quantity_available <= 0 or item['quantity'] > product.quantity_available:
            flash('Some items in your cart are out of stock or have changed. Please review your cart.', 'error')
            return redirect(url_for('cart'))

        subtotal = item['price'] * item['quantity']
        total += subtotal
        cart_items.append({
            'product': product,
            'quantity': item['quantity'],
            'price': item['price'],
            'subtotal': subtotal
        })
    
    # Create order
    order = Order(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        pickup_time=pickup_datetime,
        total_amount=total,
        status='pending'
    )
    db.session.add(order)
    db.session.flush()
    
    # Create order items and update stock
    for item in cart_items:
        order_item = OrderItem(
            order_id=order.id,
            product_id=item['product'].id,
            quantity=item['quantity'],
            price=item['price']
        )
        db.session.add(order_item)
        
        # Update product quantity
        item['product'].quantity_available -= item['quantity']
    
    db.session.commit()

    # Send email notification to seller (if email configured)
    send_order_email(order)
    
    # Clear cart
    session.pop('cart', None)
    
    flash(f'Order placed successfully! Order ID: {order.id}', 'success')
    return redirect(url_for('order_confirmation', order_id=order.id))

@app.route('/order-confirmation/<int:order_id>')
def order_confirmation(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('customer/order_confirmation.html', order=order)

@app.route('/download-bill/<int:order_id>')
def download_bill(order_id):
    order = Order.query.get_or_404(order_id)
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    story = []
    
    styles = getSampleStyleSheet()
    # Shop name and location style (top right corner)
     # Shop name and location style (top left corner)
    shop_name_style = ParagraphStyle(
        'ShopNameStyle',
        parent=styles['Normal'],
        fontSize=14,
        textColor=colors.HexColor('#2c3e50'),
        alignment=TA_LEFT,
        fontName='Helvetica-Bold',
        spaceAfter=4
    )
    shop_address_style = ParagraphStyle(
        'ShopAddressStyle',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.black,
        alignment=TA_LEFT,
        fontName='Helvetica',
        spaceAfter=10
    )
    # Shop name and location (professional format)
    shop_name = "Fathima Grocery Shop"
    shop_address = "Masuthi Street, Veeramangalam<br/>Ulundurpet Taluk, Kallakurichi District<br/>Tamil Nadu - 607202"
    story.append(Paragraph(f"<b>{shop_name}</b>", shop_name_style))
    story.append(Paragraph(shop_address, shop_address_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Order details
    order_data = [
        ['Order ID:', str(order.id)],
        ['Date:', order.created_at.strftime('%Y-%m-%d %I:%M %p')],
        ['Customer Name:', order.customer_name],
        ['Phone:', order.customer_phone],
        ['PhonePe/GPay:', '6383419864'],
        ['Pickup Time:', order.pickup_time.strftime('%Y-%m-%d %I:%M %p')],
        ['Status:', order.status.upper()]
    ]
    
    order_table = Table(order_data, colWidths=[2*inch, 4*inch])
    order_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ecf0f1')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(order_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Items table
    items_data = [['Item', 'Quantity', 'Price', 'Subtotal']]
    for item in order.items:
        items_data.append([
            item.product.name,
            str(item.quantity),
            f"${item.price:.2f}",
            f"${item.quantity * item.price:.2f}"
        ])
    
    items_table = Table(items_data, colWidths=[3*inch, 1*inch, 1*inch, 1*inch])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')])
    ]))
    story.append(items_table)
    story.append(Spacer(1, 0.2*inch))
    
    # Total
    total_style = ParagraphStyle(
        'TotalStyle',
        parent=styles['Normal'],
        fontSize=16,
        textColor=colors.HexColor('#27ae60'),
        alignment=TA_RIGHT,
        fontName='Helvetica-Bold'
    )
    story.append(Paragraph(f"<b>TOTAL: ${order.total_amount:.2f}</b>", total_style))
    story.append(Spacer(1, 0.3*inch))
   # Payment Instructions
    payment_style = ParagraphStyle(
        'PaymentStyle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#2c3e50'),
        alignment=TA_LEFT,
        fontName='Helvetica',
        spaceAfter=8,
        leftIndent=0
    )
    
    payment_title_style = ParagraphStyle(
        'PaymentTitleStyle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#2c3e50'),
        alignment=TA_LEFT,
        fontName='Helvetica-Bold',
        spaceAfter=6
    )
    
    story.append(Paragraph("<b>Payment Information:</b>", payment_title_style))
    story.append(Paragraph("If you pay online via PhonePe or GPay, please send your Order ID <b>#" + str(order.id) + "</b> in the PhonePe or GPay chatbox after completing the payment.", payment_style))
    story.append(Spacer(1, 0.2*inch))
    # Footer
    footer_style = ParagraphStyle(
        'FooterStyle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.grey,
        alignment=TA_CENTER
    )
    story.append(Paragraph("Thank you for your order! Please arrive at the scheduled pickup time.", footer_style))
    
    doc.build(story)
    buffer.seek(0)
    
    return send_file(buffer, mimetype='application/pdf', 
                    as_attachment=True, 
                    download_name=f'bill_order_{order_id}.pdf')

# Seller Routes
def seller_login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'seller_id' not in session:
            return redirect(url_for('seller_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/seller/login', methods=['GET', 'POST'])
def seller_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        seller = Seller.query.filter_by(username=username).first()
        
        if seller and seller.check_password(password):
            session['seller_id'] = seller.id
            session['seller_username'] = seller.username
            flash('Login successful!', 'success')
            return redirect(url_for('seller_dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('seller/login.html')

@app.route('/seller/logout')
def seller_logout():
    session.pop('seller_id', None)
    session.pop('seller_username', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('seller_login'))

@app.route('/seller/dashboard')
@seller_login_required
def seller_dashboard():
    total_products = Product.query.count()
    total_orders = Order.query.count()
    pending_orders = Order.query.filter_by(status='pending').count()
    total_revenue = db.session.query(db.func.sum(Order.total_amount)).scalar() or 0
    
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    
    return render_template('seller/dashboard.html',
                         total_products=total_products,
                         total_orders=total_orders,
                         pending_orders=pending_orders,
                         total_revenue=total_revenue,
                         recent_orders=recent_orders)

@app.route('/seller/products')
@seller_login_required
def seller_products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template('seller/products.html', products=products)

@app.route('/seller/products/add', methods=['POST'])
@seller_login_required
def add_product():
    name = request.form.get('name')
    description = request.form.get('description')
    price = float(request.form.get('price'))
    original_price = request.form.get('original_price')
    original_price = float(original_price) if original_price and original_price.strip() else None
    quantity = float(request.form.get('quantity'))
    unit_type = request.form.get('unit_type', 'quantity')
    
    image_path = None
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            filepath = os.path.join(PRODUCT_UPLOAD_DIR, filename)
            file.save(filepath)
            # store path relative to static folder (for url_for('static', ...))
            image_path = os.path.join('uploads', 'products', filename).replace('\\', '/')
    
    product = Product(
        name=name,
        description=description,
        price=price,
        original_price=original_price,
        quantity_available=quantity,
        unit_type=unit_type,
        image_path=image_path
    )
    db.session.add(product)
    db.session.commit()
    
    flash('Product added successfully', 'success')
    return redirect(url_for('seller_products'))

@app.route('/seller/products/update/<int:id>', methods=['POST'])
@seller_login_required
def update_product(id):
    product = Product.query.get_or_404(id)
    
    product.name = request.form.get('name')
    product.description = request.form.get('description')
    product.price = float(request.form.get('price'))
    original_price = request.form.get('original_price')
    product.original_price = float(original_price) if original_price and original_price.strip() else None
    product.quantity_available = float(request.form.get('quantity'))
    product.unit_type = request.form.get('unit_type', 'quantity')
    
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename != '' and allowed_file(file.filename):
            # Delete old image if exists
            if product.image_path:
                old_path = product.image_path
                if not old_path.startswith('static/'):
                    old_path = os.path.join('static', old_path)
                if os.path.exists(old_path):
                    os.remove(old_path)
            
            filename = secure_filename(file.filename)
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            filepath = os.path.join(PRODUCT_UPLOAD_DIR, filename)
            file.save(filepath)
            product.image_path = os.path.join('uploads', 'products', filename).replace('\\', '/')
    
    db.session.commit()
    flash('Product updated successfully', 'success')
    return redirect(url_for('seller_products'))

@app.route('/seller/products/delete/<int:id>', methods=['POST'])
@seller_login_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    
    # Delete image if exists
    if product.image_path:
        img_path = product.image_path
        if not img_path.startswith('static/'):
            img_path = os.path.join('static', img_path)
        if os.path.exists(img_path):
            os.remove(img_path)
    
    db.session.delete(product)
    db.session.commit()
    
    flash('Product deleted successfully', 'success')
    return redirect(url_for('seller_products'))

@app.route('/seller/products/out-of-stock/<int:id>', methods=['POST'])
@seller_login_required
def mark_out_of_stock(id):
    """Quick action: mark a product as out of stock by setting quantity to 0."""
    product = Product.query.get_or_404(id)
    product.quantity_available = 0.0
    db.session.commit()
    flash(f"Product '{product.name}' marked as out of stock", 'success')
    return redirect(url_for('seller_products'))

@app.route('/seller/banners')
@seller_login_required
def seller_banners():
    banners = OfferBanner.query.order_by(OfferBanner.created_at.desc()).all()
    return render_template('seller/banners.html', banners=banners)

@app.route('/seller/banners/add', methods=['POST'])
@seller_login_required
def add_banner():
    title = request.form.get('title')
    description = request.form.get('description')
    is_active = request.form.get('is_active') == 'on'
    
    image_path = None
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            filepath = os.path.join(BANNER_UPLOAD_DIR, filename)
            file.save(filepath)
            # store path relative to static folder
            image_path = os.path.join('uploads', 'banners', filename).replace('\\', '/')
    
    banner = OfferBanner(
        title=title,
        description=description,
        image_path=image_path,
        is_active=is_active
    )
    db.session.add(banner)
    db.session.commit()
    
    flash('Banner added successfully', 'success')
    return redirect(url_for('seller_banners'))

@app.route('/seller/banners/update/<int:id>', methods=['POST'])
@seller_login_required
def update_banner(id):
    banner = OfferBanner.query.get_or_404(id)
    
    banner.title = request.form.get('title')
    banner.description = request.form.get('description')
    banner.is_active = request.form.get('is_active') == 'on'
    
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename != '' and allowed_file(file.filename):
            # Delete old image if exists
            if banner.image_path:
                old_path = banner.image_path
                if not old_path.startswith('static/'):
                    old_path = os.path.join('static', old_path)
                if os.path.exists(old_path):
                    os.remove(old_path)
            
            filename = secure_filename(file.filename)
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            filepath = os.path.join(BANNER_UPLOAD_DIR, filename)
            file.save(filepath)
            banner.image_path = os.path.join('uploads', 'banners', filename).replace('\\', '/')
    
    db.session.commit()
    flash('Banner updated successfully', 'success')
    return redirect(url_for('seller_banners'))

@app.route('/seller/banners/delete/<int:id>', methods=['POST'])
@seller_login_required
def delete_banner(id):
    banner = OfferBanner.query.get_or_404(id)
    
    # Delete image if exists
    if banner.image_path and os.path.exists(banner.image_path):
        os.remove(banner.image_path)
    
    db.session.delete(banner)
    db.session.commit()
    
    flash('Banner deleted successfully', 'success')
    return redirect(url_for('seller_banners'))

@app.route('/seller/orders')
@seller_login_required
def seller_orders():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    # Format quantities for display
    for order in orders:
        for item in order.items:
            item.formatted_quantity = format_quantity(item.quantity, item.product.unit_type if item.product else 'quantity')
    return render_template('seller/orders.html', orders=orders)

def format_quantity(quantity, unit_type):
    """Format quantity for display based on unit type"""
    if unit_type == 'kg':
        if quantity == 1.0:
            return "1 kg"
        elif quantity == 0.75:
            return "750g"
        elif quantity == 0.5:
            return "500g"
        elif quantity == 0.25:
            return "250g"
        elif quantity == 0.1:
            return "100g"
        elif quantity % 1 == 0:
            return f"{int(quantity)} kg"
        else:
            # Convert to grams if less than 1kg
            grams = int(quantity * 1000)
            return f"{grams}g"
    else:
        # For quantity-based items, show as integer if whole number
        if quantity % 1 == 0:
            return str(int(quantity))
        else:
            return str(quantity)

@app.route('/seller/orders/update-status/<int:id>', methods=['POST'])
@seller_login_required
def update_order_status(id):
    order = Order.query.get_or_404(id)
    new_status = request.form.get('status')
    
    if new_status in ['pending', 'ready', 'completed']:
        order.status = new_status
        db.session.commit()
        flash('Order status updated successfully', 'success')
    
    return redirect(url_for('seller_orders'))

@app.route('/seller/orders/delete/<int:id>', methods=['POST'])
@seller_login_required
def delete_order(id):
    order = Order.query.get_or_404(id)
    
    # Delete order items (cascade should handle this, but being explicit)
    for item in order.items:
        db.session.delete(item)
    
    db.session.delete(order)
    db.session.commit()
    
    flash('Order deleted successfully', 'success')
    return redirect(url_for('seller_orders'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)

