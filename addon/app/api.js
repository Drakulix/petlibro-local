// ── API ───────────────────────────────────────────────────────────────────
async function api(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(`${BASE}${path}`, opts);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

async function loadAll() {
  try {
    [_devices, _pets, _settings] = await Promise.all([
      api("GET", "/api/devices"),
      api("GET", "/api/pets"),
      api("GET", "/api/settings"),
    ]);
  } catch(e) {
    console.error("Load error", e);
  }
}

// ── Alerts & notifications ────────────────────────────────────────────────
function deviceAlerts(device) {
  const notif = device.notifications || {};
  const alerts = [];
  if (device.device_type === "one_rfid") {
    if (notif.food_low !== false && device.online && device.surplusGrain === false) alerts.push("food_low");
    if (notif.bowl_due !== false) { const d = bowlDaysRemaining(device); if (d != null && d <= 0) alerts.push("bowl_due"); }
    if (notif.housing_due !== false) { const d = housingDaysRemaining(device); if (d != null && d <= 0) alerts.push("housing_due"); }
  } else {
    if (notif.water_low !== false) {
      const threshold = device.lowWater ?? device.low_water_grams ?? 500;
      if (device.online && device.currentWeight != null && device.currentWeight < threshold) {
        alerts.push("water_low");
      }
    }
    if (notif.filter_due !== false) {
      const days = filterDaysRemaining(device);
      if (days != null && days <= 3) alerts.push("filter_due");
    }
    if (notif.cleaning_due !== false) {
      const days = cleaningDaysRemaining(device);
      if (days != null && days <= 0) alerts.push("cleaning_due");
    }
  }
  if (notif.offline !== false && !device.online) alerts.push("offline");
  return alerts;
}

function checkAlerts() {
  let totalAlerts = 0;
  for (const device of _devices) totalAlerts += deviceAlerts(device).length;
  const badge = document.getElementById("bell-badge");
  const bellBtn = document.getElementById("btn-bell");
  const fabBell = document.getElementById("fab-bell");
  const fabBadge = document.getElementById("fab-bell-badge");
  if (totalAlerts > 0) {
    badge.textContent = totalAlerts;
    badge.style.display = "flex";
    bellBtn.style.display = "";
    fabBell.style.display = "";
    fabBell.classList.add("has-alerts");
    fabBadge.textContent = totalAlerts;
    fabBadge.style.display = "flex";
  } else {
    badge.style.display = "none";
    fabBell.style.display = "none";
    fabBell.classList.remove("has-alerts");
    fabBadge.style.display = "none";
  }
}
