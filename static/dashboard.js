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
                    <div style="display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap;">
                        <button onclick="viewQuoteAnalysis(${quote.id})" style="background: #D9FF0D; color: #00358A; padding: 8px 12px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; white-space: nowrap;">ניתוח פיננסי</button>
                        <button onclick="downloadPDF(${quote.id})" style="background: #00358A; color: white; padding: 8px 12px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; white-space: nowrap;">PDF</button>
                        <button onclick="deleteQuote(${quote.id})" style="background: #dc2626; color: white; padding: 8px 12px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; white-space: nowrap;">מחק</button>
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });

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

async function viewQuoteAnalysis(quoteId) {
    try {
        // Fetch the specific quote data
        const response = await fetch(`/api/quotes/${quoteId}`);
        if (!response.ok) {
            throw new Error('Failed to fetch quote');
        }

        const quote = await response.json();

        // Call the financial comparison function from dashboard.html
        if (typeof calculateFinancialComparison === 'function') {
            await calculateFinancialComparison(quote.system_size, quote.total_price);
            // Switch to comparison section (defined in dashboard.html)
            if (typeof showSection === 'function') {
                showSection('comparison');
            }
        } else {
            alert('פונקציית הניתוח הפיננסי לא זמינה');
        }

    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה בטעינת ניתוח פיננסי');
    }
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
