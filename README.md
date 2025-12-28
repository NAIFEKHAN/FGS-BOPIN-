# BOPIS Grocery Shop

A complete Buy Online Pickup In Store (BOPIS) system for a grocery shop with customer-facing shopping interface and seller admin panel.

## Features

### Customer Side
- Browse products with images, names, prices, and available quantities
- Add items to cart with quantity selection
- View shopping cart with item management
- Select pickup time slots during checkout
- Receive order confirmation with bill PDF download
- View active offer banners

### Seller Side
- Secure login system
- Dashboard with statistics (products, orders, revenue)
- Product management (add, edit, delete products)
- Update product quantities and prices
- Manage offer banners
- View and update order statuses

## Technology Stack

- **Backend**: Python Flask
- **Database**: SQLite
- **Frontend**: HTML, CSS, JavaScript
- **PDF Generation**: ReportLab
- **Image Processing**: Pillow

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

3. Access the application:
   - Customer side: http://localhost:5000
   - Seller login: http://localhost:5000/seller/login
   - Default seller credentials:
     - Username: `admin`
     - Password: `admin123`

## Project Structure

```
BOPIS/
├── app.py                 # Flask main application
├── models.py              # Database models
├── config.py              # Configuration
├── requirements.txt       # Python dependencies
├── static/
│   ├── css/               # Stylesheets
│   ├── js/                # JavaScript files
│   └── uploads/            # Uploaded images
├── templates/
│   ├── customer/          # Customer-facing templates
│   └── seller/            # Seller admin templates
└── database.db            # SQLite database (created automatically)
```

## Usage

### For Customers

1. Browse products on the home page
2. Add items to cart with desired quantities
3. View cart and proceed to checkout
4. Fill in customer information and select pickup time
5. Place order and download bill PDF

### For Sellers

1. Login at `/seller/login`
2. View dashboard for statistics
3. Manage products: add, edit quantities/prices, upload images
4. Manage offer banners
5. View orders and update their status (pending → ready → completed)

## Pickup Time Slots

Default pickup time slots are created automatically:
- 09:00 AM to 06:00 PM (hourly slots)
- Customers can select date and time slot during checkout
- System suggests next available date as default

## File Uploads

- Product images: `static/uploads/products/`
- Banner images: `static/uploads/banners/`
- Supported formats: PNG, JPG, JPEG, GIF, WEBP
- Maximum file size: 16MB

## Security Features

- Password hashing for seller accounts
- Session-based authentication for seller panel
- File upload validation (image types only)
- SQL injection prevention (SQLAlchemy ORM)

## Notes

- The database and upload directories are created automatically on first run
- Default seller account is created if no sellers exist
- Pickup time slots are initialized with default values
- Cart is session-based (no login required for customers)




