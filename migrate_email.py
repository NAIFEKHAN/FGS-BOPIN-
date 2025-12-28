"""
Migration script to make customer_email nullable in orders table.
Run this script once to update your database schema.
"""
from app import app, db
from models import Order

def migrate_orders_email():
    """Make customer_email nullable in orders table"""
    with app.app_context():
        try:
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            
            if 'orders' not in inspector.get_table_names():
                print("Orders table doesn't exist yet. It will be created with correct schema.")
                return
            
            # Check the table schema
            schema_info = db.session.execute(db.text(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='orders'"
            )).fetchone()
            
            if schema_info and schema_info[0]:
                schema_sql = schema_info[0]
                # Check if customer_email has NOT NULL constraint
                schema_normalized = schema_sql.replace(' ', '').replace('\n', '').replace('\t', '')
                if 'customer_emailVARCHAR(200)NOTNULL' in schema_normalized or 'customer_emailVARCHAR(200)NOT' in schema_normalized:
                    print("Migrating orders table to make customer_email nullable...")
                    
                    # Disable foreign key checks
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
                    print("✓ Successfully migrated orders table: customer_email is now nullable")
                else:
                    print("✓ Orders table already has nullable customer_email - no migration needed")
            else:
                print("Could not read orders table schema")
        except Exception as e:
            print(f"Error during migration: {e}")
            db.session.rollback()
            raise

if __name__ == '__main__':
    migrate_orders_email()


