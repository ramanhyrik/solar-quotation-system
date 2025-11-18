let currentQuoteData = {};

async function calculateQuote() {
    const systemSize = parseFloat(document.getElementById('systemSize').value);

    if (!systemSize || systemSize <= 0) {
        alert('Please enter a valid system size');
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

        // Store for later use
        currentQuoteData = {
            total_price: data.total_price,
            annual_revenue: data.annual_revenue,
            payback_period: data.payback_period,
            annual_production: data.annual_production
        };

        // Update UI
        document.getElementById('totalPrice').textContent = `₪${data.total_price.toLocaleString()}`;
        document.getElementById('annualRevenue').textContent = `₪${data.annual_revenue.toLocaleString()}`;
        document.getElementById('paybackPeriod').textContent = `${data.payback_period} years`;

        document.getElementById('calculations').style.display = 'grid';

    } catch (error) {
        console.error('Error:', error);
        alert('Error calculating quote');
    }
}

async function saveQuote() {
    const customerName = document.getElementById('customerName').value;
    const systemSize = parseFloat(document.getElementById('systemSize').value);

    if (!customerName || !systemSize) {
        alert('Please fill in required fields (Customer Name and System Size)');
        return;
    }

    if (!currentQuoteData.total_price) {
        alert('Please calculate the quote first');
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
            alert('Quote saved successfully!');
            // Clear form
            document.querySelectorAll('input').forEach(input => input.value = '');
            document.getElementById('calculations').style.display = 'none';
            currentQuoteData = {};
        } else {
            alert('Error saving quote');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error saving quote');
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
                <td>${quote.system_size} kWp</td>
                <td>₪${quote.total_price.toLocaleString()}</td>
                <td>${new Date(quote.created_at).toLocaleDateString()}</td>
                <td>
                    <button onclick="downloadPDF(${quote.id})" style="background: #667eea; color: white; margin-right: 8px;">Download PDF</button>
                    <button onclick="deleteQuote(${quote.id})" class="delete">Delete</button>
                </td>
            `;
            tbody.appendChild(row);
        });

        document.querySelector('.quote-form').style.display = 'none';
        document.getElementById('quoteHistory').style.display = 'block';

    } catch (error) {
        console.error('Error:', error);
        alert('Error loading quote history');
    }
}

async function deleteQuote(id) {
    if (!confirm('Are you sure you want to delete this quote?')) {
        return;
    }

    try {
        const response = await fetch(`/api/quotes/${id}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            loadQuoteHistory();
        } else {
            alert('Error deleting quote');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error deleting quote');
    }
}

function downloadPDF(quoteId) {
    window.location.href = `/api/quotes/${quoteId}/pdf`;
}

async function generatePDF() {
    const customerName = document.getElementById('customerName').value;
    const systemSize = parseFloat(document.getElementById('systemSize').value);

    if (!customerName || !systemSize) {
        alert('Please fill in required fields (Customer Name and System Size) and calculate first');
        return;
    }

    if (!currentQuoteData.total_price) {
        alert('Please calculate the quote first');
        return;
    }

    // First, save the quote
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
        // Save quote first
        const response = await fetch('/api/quotes', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(quoteData)
        });

        if (!response.ok) {
            throw new Error('Failed to save quote');
        }

        const result = await response.json();
        const quoteId = result.quote_id;

        // Generate and download PDF
        window.location.href = `/api/quotes/${quoteId}/pdf`;

        alert('PDF generated and downloading!');

    } catch (error) {
        console.error('Error:', error);
        alert('Error generating PDF. Please try again.');
    }
}
