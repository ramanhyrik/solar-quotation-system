let currentQuoteData = {};

async function calculateQuote() {
    const systemSize = parseFloat(document.getElementById('systemSize').value);

    if (!systemSize || systemSize <= 0) {
        alert('נא להזין גודל מערכת תקין');
        return;
    }

    try {
        const formData = new FormData();
        formData.append('system_size', systemSize);

        const response = await fetch('/api/calculate', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        // שמירה לשימוש מאוחר יותר
        currentQuoteData = {
            total_price: data.total_price,
            annual_revenue: data.annual_revenue,
            payback_period: data.payback_period,
            annual_production: data.annual_production
        };

        // עדכון ממשק
        document.getElementById('totalPrice').textContent = `₪${data.total_price.toLocaleString()}`;
        document.getElementById('annualRevenue').textContent = `₪${data.annual_revenue.toLocaleString()}`;
        document.getElementById('paybackPeriod').textContent = `${data.payback_period} שנים`;

        document.getElementById('calculations').style.display = 'grid';

    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה בחישוב הצעה');
    }
}

async function saveQuote() {
    const customerName = document.getElementById('customerName').value;
    const systemSize = parseFloat(document.getElementById('systemSize').value);

    if (!customerName || !systemSize) {
        alert('נא למלא שדות חובה (שם לקוח וגודל מערכת)');
        return;
    }

    if (!currentQuoteData.total_price) {
        alert('נא לחשב את ההצעה קודם');
        return;
    }

    const quoteData = {
        customer_name: customerName,
        customer_phone: document.getElementById('customerPhone').value,
        customer_email: document.getElementById('customerEmail').value,
        customer_address: document.getElementById('customerAddress').value,
        system_size: systemSize,
        roof_area: parseFloat(document.getElementById('roofArea').value) || null,
        annual_production: currentQuoteData.annual_production,
        panel_type: document.getElementById('panelType').value,
        panel_count: parseInt(document.getElementById('panelCount').value) || null,
        inverter_type: document.getElementById('inverterType').value,
        direction: document.getElementById('direction').value,
        tilt_angle: parseFloat(document.getElementById('tiltAngle').value) || null,
        warranty_years: parseInt(document.getElementById('warrantyYears').value) || 25,
        total_price: currentQuoteData.total_price,
        annual_revenue: currentQuoteData.annual_revenue,
        payback_period: currentQuoteData.payback_period
    };

    try {
        const response = await fetch('/api/quotes', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(quoteData)
        });

        if (response.ok) {
            alert('ההצעה נשמרה בהצלחה!');
            // ניקוי טופס
            document.querySelectorAll('input').forEach(input => input.value = '');
            document.getElementById('calculations').style.display = 'none';
            currentQuoteData = {};
        } else {
            alert('שגיאה בשמירת הצעה');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה בשמירת הצעה');
    }
}

async function loadQuoteHistory() {
    try {
        const response = await fetch('/api/quotes');
        const data = await response.json();

        const tbody = document.querySelector('#quotesTable tbody');
        tbody.innerHTML = '';

        data.quotes.forEach(quote => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${quote.quote_number}</td>
                <td>${quote.customer_name}</td>
                <td>${quote.system_size} קוט״ש</td>
                <td>₪${quote.total_price.toLocaleString()}</td>
                <td>${new Date(quote.created_at).toLocaleDateString('he-IL')}</td>
                <td>
                    <button onclick="downloadPDF(${quote.id})" style="background: #00358A; color: white; margin-left: 8px;">הורד PDF</button>
                    <button onclick="deleteQuote(${quote.id})" class="delete">מחק</button>
                </td>
            `;
            tbody.appendChild(row);
        });

        document.querySelector('.quote-form').style.display = 'none';
        document.getElementById('quoteHistory').style.display = 'block';

    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה בטעינת היסטוריית הצעות');
    }
}

async function deleteQuote(id) {
    if (!confirm('האם אתה בטוח שברצונך למחוק הצעה זו?')) {
        return;
    }

    try {
        const response = await fetch(`/api/quotes/${id}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            loadQuoteHistory();
        } else {
            alert('שגיאה במחיקת הצעה');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה במחיקת הצעה');
    }
}

function downloadPDF(quoteId) {
    window.location.href = `/api/quotes/${quoteId}/pdf`;
}

async function generatePDF() {
    const customerName = document.getElementById('customerName').value;
    const systemSize = parseFloat(document.getElementById('systemSize').value);

    if (!customerName || !systemSize) {
        alert('נא למלא שדות חובה (שם לקוח וגודל מערכת) ולחשב קודם');
        return;
    }

    if (!currentQuoteData.total_price) {
        alert('נא לחשב את ההצעה קודם');
        return;
    }

    // קודם, שמור את ההצעה
    const quoteData = {
        customer_name: customerName,
        customer_phone: document.getElementById('customerPhone').value,
        customer_email: document.getElementById('customerEmail').value,
        customer_address: document.getElementById('customerAddress').value,
        system_size: systemSize,
        roof_area: parseFloat(document.getElementById('roofArea').value) || null,
        annual_production: currentQuoteData.annual_production,
        panel_type: document.getElementById('panelType').value,
        panel_count: parseInt(document.getElementById('panelCount').value) || null,
        inverter_type: document.getElementById('inverterType').value,
        direction: document.getElementById('direction').value,
        tilt_angle: parseFloat(document.getElementById('tiltAngle').value) || null,
        warranty_years: parseInt(document.getElementById('warrantyYears').value) || 25,
        total_price: currentQuoteData.total_price,
        annual_revenue: currentQuoteData.annual_revenue,
        payback_period: currentQuoteData.payback_period
    };

    try {
        // שמירת הצעה קודם
        const response = await fetch('/api/quotes', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(quoteData)
        });

        if (!response.ok) {
            throw new Error('נכשל בשמירת הצעה');
        }

        const result = await response.json();
        const quoteId = result.quote_id;

        // יצירת והורדת PDF
        window.location.href = `/api/quotes/${quoteId}/pdf`;

        alert('ה-PDF נוצר ומוריד!');

    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה ביצירת PDF. נסה שוב.');
    }
}
