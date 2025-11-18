# ☀️ Solar Quotation System

**Simple, Powerful, Self-Contained** solar energy quotation system using Python + SQLite + HTML.

## Features

✅ **Web Calculator** - Public-facing calculator for instant quotes
✅ **Sales Dashboard** - Generate professional quotes during customer calls
✅ **Admin Panel** - Manage pricing, company settings
✅ **Quote Management** - Save, view, and track all quotes
✅ **Automated Calculations** - Instant price, revenue, and payback calculations
✅ **SQLite Database** - Zero external dependencies
✅ **Pure HTML/CSS/JS** - No complex frameworks
✅ **Python FastAPI** - Fast, modern backend

## Quick Start (5 Minutes)

### 1. Install Python 3.8+

Download from [python.org](https://python.org)

### 2. One-Command Start

```bash
python start.py
```

That's it! The script will:
- Install dependencies if needed
- Initialize the database
- Start the server
- Show you the login credentials

**Or do it manually:**

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database
python database.py

# Run application
python main.py
```

### 3. Open in Browser

Visit: [http://localhost:8000](http://localhost:8000)

**Default Login:**
- Email: `admin@solar.com`
- Password: `admin123`

**Done!** 🎉

## Project Structure

```
solar-quotation-system/
├── main.py                 # FastAPI application
├── database.py             # Database setup and helpers
├── requirements.txt        # Python dependencies
├── solar_quotes.db         # SQLite database (created automatically)
├── templates/
│   ├── index.html         # Public calculator
│   ├── login.html         # Login page
│   ├── dashboard.html     # Sales dashboard
│   └── admin.html         # Admin panel
└── static/
    ├── dashboard.css      # Styles
    └── dashboard.js       # Dashboard JavaScript
```

## Usage

### For Website Visitors

1. Visit [http://localhost:8000](http://localhost:8000)
2. Enter system size (kWp)
3. Click "Calculate Quote"
4. See instant pricing and environmental impact

### For Sales Representatives

1. Login at [http://localhost:8000/login](http://localhost:8000/login)
2. Fill in customer information
3. Enter system size - calculations happen automatically
4. Add technical details (panels, inverters, etc.)
5. Click "Save Quote"

### For Administrators

1. Login with admin account
2. Go to Admin Panel
3. Configure:
   - Pricing parameters (price per kWp, tariff rates, etc.)
   - Company information (name, contact details)

## Pricing Calculations

### Default Formula

```python
# Based on Israeli market
Price = System Size (kWp) × 4,130 ILS
Annual Revenue = System Size × 1,360 kWh × 0.48 ILS/kWh
Payback Period = Price / Annual Revenue

# Example: 15 kWp system
Price = 15 × 4,130 = 61,950 ILS
Revenue = 15 × 1,360 × 0.48 = 9,792 ILS/year
Payback = 61,950 / 9,792 = 6.3 years
```

**All parameters are editable in the Admin Panel!**

## Deployment

### Option 1: Local Server

```bash
# Run on specific port
python main.py
# or
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Option 2: Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t solar-quotation .
docker run -p 8000:8000 -v $(pwd)/solar_quotes.db:/app/solar_quotes.db solar-quotation
```

### Option 3: Render.com (Free)

1. Create account at [render.com](https://render.com)
2. Connect your GitHub repository
3. Create new "Web Service"
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

### Option 4: PythonAnywhere

1. Upload files to [pythonanywhere.com](https://pythonanywhere.com)
2. Set up WSGI configuration
3. Run `python database.py` in console
4. Start web app

## Database Schema

### Tables

**users** - System users
- id, email, password, name, role, created_at

**quotes** - Customer quotations
- id, quote_number, customer_info, system_specs, pricing, created_at

**pricing_parameters** - Configurable pricing
- price_per_kwp, production_per_kwp, tariff_rate, vat_rate

**company_settings** - Company information
- company_name, contact_details, branding

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Homepage calculator |
| GET | `/login` | Login page |
| POST | `/api/login` | Authenticate user |
| GET | `/logout` | Logout |
| GET | `/dashboard` | Sales dashboard |
| GET | `/admin` | Admin panel |
| POST | `/api/calculate` | Calculate quote |
| GET | `/api/quotes` | List all quotes |
| POST | `/api/quotes` | Create quote |
| DELETE | `/api/quotes/{id}` | Delete quote |
| GET | `/api/pricing` | Get pricing parameters |
| POST | `/api/pricing` | Update pricing |
| GET | `/api/company` | Get company settings |
| POST | `/api/company` | Update company |

## Customization

### Change Pricing Formula

Edit `database.py` defaults or use Admin Panel:

```python
price_per_kwp = 4130       # Your price
production_per_kwp = 1360  # Your climate data
tariff_rate = 0.48         # Your electricity rate
```

### Add Your Branding

1. Login as admin
2. Go to Admin Panel
3. Update company name, contact info
4. Customize colors in CSS files

### Modify Calculator

Edit `templates/index.html` to add/remove fields

## Security

- ✅ Password hashing (SHA-256)
- ✅ Session management
- ✅ Role-based access control
- ✅ HTTPS ready (use reverse proxy)
- ✅ SQL injection prevention

**For Production:**
- Use stronger password hashing (bcrypt)
- Add HTTPS with nginx/Apache
- Set secure session cookies
- Add rate limiting
- Regular backups of SQLite database

## Backup

### Backup Database

```bash
# Simple backup
cp solar_quotes.db solar_quotes_backup_$(date +%Y%m%d).db

# Automated daily backup (cron)
0 2 * * * cp /path/to/solar_quotes.db /backup/solar_quotes_$(date +\%Y\%m\%d).db
```

## Troubleshooting

### "Module not found"
```bash
pip install -r requirements.txt
```

### "Database is locked"
- Only one process can write at a time
- Use connection pooling for high traffic
- Consider PostgreSQL for production

### "Port already in use"
```bash
python main.py --port 8001
# or
uvicorn main:app --port 8001
```

## Development

### Add New Features

1. **Add database table**: Edit `database.py`
2. **Add API endpoint**: Edit `main.py`
3. **Add UI**: Create/edit templates
4. **Add styles**: Edit static CSS/JS

### Example: Add Email Feature

```python
# In main.py
@app.post("/api/send-quote")
async def send_quote_email(quote_id: int):
    # Your email logic here
    pass
```

## Tech Stack

- **Backend**: Python 3.8+ with FastAPI
- **Database**: SQLite3 (built-in)
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Templating**: Jinja2
- **PDF**: ReportLab (optional)

## Why This Stack?

✅ **Zero external dependencies** (no PostgreSQL, no Node.js)
✅ **Easy to deploy** (single Python process)
✅ **Fast** (FastAPI is very fast)
✅ **Simple** (no complex build process)
✅ **Portable** (runs anywhere Python runs)
✅ **Free** (all open-source tools)

## Limitations

- SQLite: Single-writer limitation (fine for most cases)
- No built-in PDF generation (can add ReportLab)
- Basic authentication (no OAuth)
- In-memory sessions (restart clears sessions)

**For high-traffic production:**
- Upgrade to PostgreSQL
- Add Redis for sessions
- Implement proper authentication
- Add load balancing

## Support

### Documentation
- FastAPI: https://fastapi.tiangolo.com
- SQLite: https://www.sqlite.org/docs.html
- Jinja2: https://jinja.palletsprojects.com

### Common Issues
1. Check Python version: `python --version` (need 3.8+)
2. Check dependencies: `pip list`
3. Check database: `python database.py`
4. Check logs in terminal

## License

Open source - Use freely for your solar company!

## Credits

Built with ❤️ using:
- FastAPI - Modern Python web framework
- SQLite - Reliable embedded database
- HTML/CSS/JS - Universal web technologies

---

**Ready to generate professional solar quotes!** ☀️

For questions or issues, check the code comments or FastAPI documentation.
