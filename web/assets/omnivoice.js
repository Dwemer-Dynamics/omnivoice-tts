const state = {
  status: null,
  languages: null,
  activeLanguage: "sk",
  selectedJob: null,
};

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(`api/${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  if (!response.ok && response.headers.get("content-type")?.includes("application/json")) {
    return response.json();
  }
  return response;
}

async function jsonApi(path, body = null) {
  const options = body ? { method: "POST", body: JSON.stringify(body) } : {};
  const response = await api(path, options);
  if (response instanceof Response) {
    return response.json();
  }
  return response;
}

function setText(id, value, className = "") {
  const node = $(id);
  if (!node) {
    return;
  }
  node.textContent = value;
  node.className = className;
}

function profiles() {
  return state.languages?.profiles || [];
}

function presets() {
  return state.languages?.presets || [];
}

function profileById(id) {
  return profiles().find((item) => item.id === id) || null;
}

function currentLanguage() {
  const select = $("profileSelect");
  return select?.value || state.activeLanguage || profiles()[0]?.id || "sk";
}

function selectedPreset() {
  const select = $("presetSelect");
  if (!select || select.selectedOptions[0]?.disabled) {
    return "";
  }
  return select.value || "";
}

function currentProfile() {
  return profileById(currentLanguage());
}

function setLanguageActionState() {
  const hasProfile = Boolean(currentProfile());
  for (const id of ["setActive", "refreshVoices", "calibrateVoice", "buildVoice", "buildFull", "generateTest"]) {
    const button = $(id);
    if (button) {
      button.disabled = !hasProfile;
      button.title = hasProfile ? "" : "Install a language profile first.";
    }
  }
}

async function loadStatus() {
  const data = await jsonApi("status.php");
  state.status = data;
  const health = data.health || {};
  const active = health.active_language || {};
  state.activeLanguage = active.id || data.config?.active_language || state.activeLanguage;

  setText("serviceState", data.running ? "Running" : "Stopped", data.running ? "ok" : "warn");
  setText("startupState", data.startup_enabled ? "Enabled" : "Disabled", data.startup_enabled ? "ok" : "warn");
  setText("activeLanguage", active.display_name ? `${active.display_name} (${active.id})` : state.activeLanguage);
  setText("voiceCount", String(health.voice_count ?? 0), (health.voice_count || 0) > 0 ? "ok" : "warn");
  setText("gpuName", health.gpu || "Unknown", health.cuda ? "ok" : "warn");
}

function renderProfileOptions() {
  const select = $("profileSelect");
  if (!select) {
    return;
  }
  select.innerHTML = "";

  const configuredProfiles = profiles().slice().sort((a, b) => String(a.id).localeCompare(String(b.id)));
  for (const profile of configuredProfiles) {
    const option = document.createElement("option");
    option.value = profile.id;
    option.textContent = `${profile.id} - ${profile.display_name || profile.id}`;
    if (profile.id === state.activeLanguage) {
      option.selected = true;
    }
    select.append(option);
  }

  if (!select.value && configuredProfiles.length > 0) {
    select.value = configuredProfiles[0].id;
  }
  updateLanguageMeta();
}

function renderPresetOptions() {
  const select = $("presetSelect");
  const search = $("languageSearch")?.value.trim().toLowerCase() || "";
  if (!select) {
    return;
  }
  select.innerHTML = "";

  const installed = new Set(profiles().map((profile) => profile.id));
  let firstAvailable = "";
  for (const preset of presets()) {
    const label = `${preset.id} - ${preset.display_name || preset.omnivoice_language || ""}`;
    const haystack = `${label} ${(preset.aliases || []).join(" ")}`.toLowerCase();
    if (search && !haystack.includes(search)) {
      continue;
    }
    const option = document.createElement("option");
    option.value = preset.id;
    option.textContent = installed.has(preset.id) ? `${label} (installed)` : label;
    option.disabled = installed.has(preset.id);
    if (!option.disabled && !firstAvailable) {
      firstAvailable = preset.id;
    }
    select.append(option);
  }
  if (firstAvailable) {
    select.value = firstAvailable;
  }
  updatePresetMeta();
}

function updateLanguageMeta() {
  const profile = currentProfile();
  if (!profile) {
    $("languageMeta").textContent = "No installed language profiles found. Add a language first.";
    setText("libraryLanguage", "");
    setLanguageActionState();
    return;
  }

  const placeholder = profile.placeholder ? "placeholder text present" : "ready profile";
  $("languageMeta").textContent = `${profile.display_name || profile.id}: OmniVoice ${profile.omnivoice_language || "unknown"}, Whisper ${profile.whisper_language || "unknown"}; ${placeholder}`;
  setText("libraryLanguage", `${profile.display_name || profile.id} (${profile.id})`);
  setLanguageActionState();
}

function updatePresetMeta() {
  const preset = presets().find((item) => item.id === selectedPreset());
  if (!preset) {
    $("presetMeta").textContent = "";
    return;
  }
  const nativeSamples = preset.has_native_samples === false ? "placeholder samples" : "native calibration samples";
  $("presetMeta").textContent = `${preset.display_name || preset.id}: ${preset.omnivoice_language || "OmniVoice"} / ${preset.whisper_language || "Whisper"}; ${nativeSamples}`;
}

async function loadLanguages() {
  state.languages = await jsonApi("languages.php");
  state.activeLanguage = state.languages.active_language || state.activeLanguage;
  renderProfileOptions();
  renderPresetOptions();
}

async function languageAction(action, extra = {}) {
  const payload = { action, ...extra };
  const result = await jsonApi("languages.php", payload);
  if (!result.ok) {
    alert(result.result?.stderr || result.error || "Language action failed.");
    return false;
  }
  await Promise.all([loadLanguages(), loadStatus()]);
  return true;
}

async function startJob(action, extra = {}) {
  const result = await jsonApi("jobs.php", { action, ...extra });
  if (!result.ok) {
    alert(result.error || "Job failed to start.");
    return;
  }
  state.selectedJob = result.job?.id || null;
  await loadJobs();
}

async function loadVoices(refresh = false) {
  const lang = currentLanguage();
  const profile = profileById(lang);
  const tbody = $("voiceRows");
  tbody.innerHTML = "";

  if (!profile) {
    $("voiceSummary").textContent = "Install a language profile before auditing voices.";
    return;
  }

  const data = await jsonApi(`voices.php?language=${encodeURIComponent(lang)}&refresh=${refresh ? "1" : "0"}`);
  const report = data.report;
  if (!report) {
    $("voiceSummary").textContent = "No audit report exists yet.";
    return;
  }
  const summary = report.summary || {};
  $("voiceSummary").textContent = `Total ${summary.total_directories || 0}; ready ${summary.runtime_ready || 0}; calibrated ${summary.calibrated || 0}; warnings ${summary.with_warnings || 0}; broken ${summary.broken || 0}`;
  for (const voice of (report.voices || []).slice(0, 300)) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(voice.name || "")}</td>
      <td class="${voice.runtime_ready ? "ok" : "warn"}">${escapeHtml(voice.status || "")}</td>
      <td>${voice.calibrated ? "yes" : "no"}</td>
      <td>${escapeHtml([...(voice.errors || []), ...(voice.warnings || [])].join("; "))}</td>
    `;
    tbody.append(row);
  }
}

async function loadJobs() {
  const data = await jsonApi("jobs.php");
  const list = $("jobList");
  list.innerHTML = "";
  for (const job of data.jobs || []) {
    const item = document.createElement("div");
    item.className = "job-item";
    item.innerHTML = `<strong>${escapeHtml(job.label || job.id)}</strong><span class="${job.state === "completed" ? "ok" : job.state === "failed" ? "fail" : "warn"}">${escapeHtml(job.state || "unknown")}</span> <span>${escapeHtml(job.created_at_utc || "")}</span>`;
    item.addEventListener("click", async () => {
      state.selectedJob = job.id;
      await loadJob(job.id);
    });
    list.append(item);
  }
  if (state.selectedJob) {
    await loadJob(state.selectedJob);
  }
}

async function loadJob(id) {
  const data = await jsonApi(`jobs.php?id=${encodeURIComponent(id)}`);
  $("jobLog").textContent = data.job?.log_tail || "";
}

async function generateTest() {
  const profile = currentProfile();
  if (!profile) {
    alert("Install a language profile before testing voice synthesis.");
    return;
  }

  const response = await api("test_voice.php", {
    method: "POST",
    body: JSON.stringify({
      text: $("testText").value,
      voice: $("testVoice").value,
      language: profile.id,
    }),
  });
  if (!(response instanceof Response) || !response.ok) {
    alert("Synthesis failed.");
    return;
  }
  const blob = await response.blob();
  const audio = $("audioPlayer");
  audio.src = URL.createObjectURL(blob);
  await audio.play();
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}

function wireEvents() {
  $("refreshStatus").addEventListener("click", loadStatus);
  $("runDoctor").addEventListener("click", () => startJob("doctor"));
  $("startService").addEventListener("click", () => startJob("start_service"));
  $("loadLanguages").addEventListener("click", loadLanguages);
  $("languageSearch").addEventListener("input", renderPresetOptions);
  $("presetSelect").addEventListener("change", updatePresetMeta);
  $("profileSelect").addEventListener("change", async () => {
    updateLanguageMeta();
    await loadVoices(false);
  });
  $("enablePreset").addEventListener("click", async () => {
    const preset = selectedPreset();
    if (!preset) {
      alert("Select a language preset first.");
      return;
    }
    const ok = await languageAction("enable_preset", {
      preset,
      allow_placeholder: $("allowPlaceholder").checked,
    });
    if (ok) {
      $("profileSelect").value = preset;
      updateLanguageMeta();
      await loadVoices(false);
    }
  });
  $("setActive").addEventListener("click", () => languageAction("set_active", { language: currentLanguage() }));
  $("enableStartup").addEventListener("click", () => startJob("enable_startup"));
  $("disableStartup").addEventListener("click", () => startJob("disable_startup"));
  $("refreshVoices").addEventListener("click", () => loadVoices(true));
  $("calibrateVoice").addEventListener("click", () => startJob("calibrate_voice", { language: currentLanguage(), voice: $("voiceId").value }));
  $("buildVoice").addEventListener("click", () => startJob("build_voice", { language: currentLanguage(), voice: $("voiceId").value }));
  $("buildFull").addEventListener("click", () => {
    if (confirm(`Build the full ${currentLanguage()} library? This can take a long time.`)) {
      startJob("build_full", { language: currentLanguage() });
    }
  });
  $("generateTest").addEventListener("click", generateTest);
  $("refreshJobs").addEventListener("click", loadJobs);
}

async function boot() {
  wireEvents();
  await Promise.all([loadStatus(), loadLanguages(), loadJobs()]);
  await loadVoices(false);
  setInterval(loadStatus, 10000);
  setInterval(loadJobs, 5000);
}

boot().catch((error) => {
  console.error(error);
  alert("OmniVoice UI failed to load. Check the browser console and Apache logs.");
});
