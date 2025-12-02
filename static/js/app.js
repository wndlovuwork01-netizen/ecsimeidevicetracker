// Theme toggle
document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.getElementById('themeToggle');
  const body = document.body;
  toggle?.addEventListener('click', () => {
    if (body.classList.contains('theme-dark')) {
      body.classList.remove('theme-dark');
      body.classList.add('theme-light');
    } else {
      body.classList.remove('theme-light');
      body.classList.add('theme-dark');
    }
  });

  // Map rendering if element exists
  const mapEl = document.getElementById('map');
  if (mapEl) {
    const lat = parseFloat(mapEl.dataset.lat);
    const lng = parseFloat(mapEl.dataset.lng);
    if (!isNaN(lat) && !isNaN(lng)) {
      const map = L.map('map').setView([lat, lng], 14);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors'
      }).addTo(map);
      L.marker([lat, lng]).addTo(map).bindPopup('Last known location').openPopup();

      // Draw path history if available
      if (window.DEVICE_LOCATIONS && Array.isArray(window.DEVICE_LOCATIONS) && window.DEVICE_LOCATIONS.length > 0) {
        const points = window.DEVICE_LOCATIONS.map(d => [d.lat, d.lng]);
        const poly = L.polyline(points, { color: '#1e60d9' }).addTo(map);
        map.fitBounds(poly.getBounds(), { padding: [20, 20] });
      }
    }
  }
});