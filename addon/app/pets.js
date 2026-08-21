// ── Pets ──────────────────────────────────────────────────────────────────
function renderPets() {
  const key = JSON.stringify(_pets.map(p => ({ id: p.id, name: p.name, breed: p.breed, w: p.weight_kg, img: p.image_url })));
  if (key === _lastPetRenderKey) return;
  _lastPetRenderKey = key;
  populateSortSelect();

  const list = document.getElementById("pet-list");
  if (!_pets.length) {
    list.innerHTML = `<div class="empty-state">
      <div class="empty-icon">🐾</div>
      <div class="empty-msg">${t("pet.none")}</div>
    </div>`;
    return;
  }
  list.innerHTML = _pets.map(p => `<div class="pet-card" data-pet-id="${escHtml(p.id)}">
    <div class="pet-avatar">${p.image_url ? `<img src="${escHtml(p.image_url)}" alt="">` : "🐾"}</div>
    <div class="pet-info">
      <div class="pet-name">${escHtml(p.name || "Unnamed pet")}</div>
      <div class="pet-sub">${escHtml(p.breed || "")}${p.weight_kg ? ` · ${useImperial() ? (p.weight_kg * 2.20462).toFixed(1) + " lbs" : p.weight_kg + " kg"}` : ""}</div>
    </div>
  </div>`).join("");

  list.querySelectorAll(".pet-card").forEach(card => {
    card.addEventListener("click", () => {
      const pet = _pets.find(p => p.id === card.dataset.petId);
      if (pet) openPetModal(pet);
    });
  });
}

let _pendingPetPhoto = null;  // Blob set after crop, uploaded on save

function openPetModal(pet) {
  _editPetId = pet ? pet.id : null;
  _pendingPetPhoto = null;
  document.getElementById("pet-modal-title").textContent = pet ? pet.name : t("pet.add");
  document.getElementById("p-name").value = pet ? (pet.name || "") : "";
  document.getElementById("p-breed").value = pet ? (pet.breed || "") : "";
  document.getElementById("p-photo-file").value = "";

  // Weight: store in kg, display in lbs if imperial
  const imperial = useImperial();
  const weightLabel = document.getElementById("p-weight-label");
  const weightInput = document.getElementById("p-weight");
  if (imperial) {
    weightLabel.textContent = t("weight.lbs");
    weightInput.placeholder = "10.0";
    const rawKg = pet ? (pet.weight_kg || null) : null;
    weightInput.value = rawKg != null ? (rawKg * 2.20462).toFixed(1) : "";
  } else {
    weightLabel.textContent = t("weight.kg");
    weightInput.placeholder = "4.5";
    weightInput.value = pet ? (pet.weight_kg || "") : "";
  }

  // Pet photo — image_url is already a full path (includes ingress prefix), use it directly
  const preview = document.getElementById("pet-photo-preview");
  const placeholder = document.getElementById("pet-photo-placeholder");
  if (pet?.image_url) {
    preview.src = pet.image_url;
    preview.style.display = "";
    placeholder.style.display = "none";
  } else {
    preview.src = "";
    preview.style.display = "none";
    placeholder.style.display = "";
  }

  // Device assignment checkboxes
  const deviceSection = document.getElementById("p-device-section");
  const deviceList = document.getElementById("p-device-list");
  const assignedSerials = new Set(pet?.device_serials || []);
  // Also collect serials from device.pet_ids for this pet
  if (pet) {
    _devices.forEach(d => { if (d.pet_ids?.includes(pet.id)) assignedSerials.add(d.serial); });
  }
  if (_devices.length > 0) {
    deviceSection.style.display = "";
    deviceList.innerHTML = _devices.map(d => `
      <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:14px">
        <input type="checkbox" class="p-device-cb" value="${escHtml(d.serial)}"
          ${assignedSerials.has(d.serial) ? "checked" : ""}
          style="width:16px;height:16px;accent-color:var(--pl-accent)">
        <span>${escHtml(d.name || d.device_type || d.serial)}</span>
        ${d.room ? `<span style="font-size:12px;color:var(--pl-subtext)">(${escHtml(d.room)})</span>` : ""}
      </label>
    `).join("");
  } else {
    deviceSection.style.display = "none";
  }

  document.getElementById("btn-pet-delete").style.display = pet ? "" : "none";
  document.getElementById("modal-pet").classList.add("open");
}

async function savePet() {
  const imperial = useImperial();
  const rawWeight = parseFloat(document.getElementById("p-weight").value);
  const weight_kg = isNaN(rawWeight) ? null : (imperial ? rawWeight / 2.20462 : rawWeight);

  const body = {
    name: document.getElementById("p-name").value.trim(),
    breed: document.getElementById("p-breed").value.trim(),
    weight_kg: weight_kg != null ? parseFloat(weight_kg.toFixed(3)) : null,
  };
  try {
    let savedPet;
    if (_editPetId) {
      savedPet = await api("POST", `/api/pets/${_editPetId}`, body);
    } else {
      savedPet = await api("POST", "/api/pets", body);
    }
    const petId = savedPet?.id || _editPetId;

    // Upload photo if one was cropped
    if (_pendingPetPhoto && petId) {
      try {
        const formData = new FormData();
        formData.append("image", _pendingPetPhoto, "pet.png");
        const r = await fetch(`${BASE}/api/pets/${petId}/image`, { method: "POST", body: formData });
        if (!r.ok) console.warn("Pet photo upload failed:", r.status);
      } catch(e) { console.warn("Pet photo upload error:", e); }
    }

    // Sync device assignment: update pet_ids on each device
    const checkedSerials = new Set(
      Array.from(document.querySelectorAll(".p-device-cb:checked")).map(cb => cb.value)
    );
    const allSerials = new Set(
      Array.from(document.querySelectorAll(".p-device-cb")).map(cb => cb.value)
    );
    for (const serial of allSerials) {
      const dev = _devices.find(d => d.serial === serial);
      if (!dev) continue;
      const currentIds = new Set(dev.pet_ids || []);
      const shouldHave = checkedSerials.has(serial);
      const doesHave = petId && currentIds.has(petId);
      if (shouldHave && !doesHave) {
        const newIds = [...currentIds, petId];
        await api("POST", `/api/devices/${serial}`, { pet_ids: newIds });
      } else if (!shouldHave && doesHave) {
        const newIds = [...currentIds].filter(id => id !== petId);
        await api("POST", `/api/devices/${serial}`, { pet_ids: newIds });
      }
    }

    document.getElementById("modal-pet").classList.remove("open");
    _pendingPetPhoto = null;
    await refresh();
  } catch(e) { alert(t("pet.save_failed", {error: e.message})); }
}

async function deletePet() {
  if (!confirm(t("pet.delete_confirm"))) return;
  await api("DELETE", `/api/pets/${_editPetId}`);
  document.getElementById("modal-pet").classList.remove("open");
  await refresh();
}
