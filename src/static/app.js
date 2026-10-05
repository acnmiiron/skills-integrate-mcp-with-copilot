document.addEventListener("DOMContentLoaded", () => {
  const activitiesList = document.getElementById("activities-list");
  const activitySelect = document.getElementById("activity");
  const signupForm = document.getElementById("signup-form");
  const messageDiv = document.getElementById("message");
  const loginForm = document.getElementById("staff-login-form");
  const staffMessage = document.getElementById("staff-message");
  const staffSession = document.getElementById("staff-session");
  const staffIdentity = document.getElementById("staff-identity");
  const organizerAdmin = document.getElementById("organizer-admin");
  const organizerCreateForm = document.getElementById("organizer-create-form");
  const organizerAssignments = document.getElementById("organizer-assignments");
  const organizersList = document.getElementById("organizers-list");

  let staffToken = null;
  let currentStaff = null;
  let activityNames = [];

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[character]);
  }

  function showMessage(element, text, type) {
    element.textContent = text;
    element.className = type;
    element.classList.remove("hidden");
    setTimeout(() => element.classList.add("hidden"), 5000);
  }

  async function apiFetch(url, options = {}) {
    const headers = new Headers(options.headers || {});
    if (staffToken) {
      headers.set("Authorization", `Bearer ${staffToken}`);
    }
    if (options.body) {
      headers.set("Content-Type", "application/json");
    }
    const response = await fetch(url, { ...options, headers });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || "The request could not be completed");
    }
    return result;
  }

  function canManageActivity(name) {
    return currentStaff && (
      currentStaff.role === "admin" ||
      currentStaff.assignments.includes(name)
    );
  }

  function renderActivityOptions() {
    activitySelect.innerHTML = '<option value="">-- Select an activity --</option>';
    organizerAssignments.innerHTML = "";
    activityNames.forEach((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      activitySelect.appendChild(option);

      const assignment = document.createElement("option");
      assignment.value = name;
      assignment.textContent = name;
      organizerAssignments.appendChild(assignment);
    });
  }

  function renderActivities(activities) {
    activityNames = Object.keys(activities);
    renderActivityOptions();
    activitiesList.innerHTML = "";

    Object.entries(activities).forEach(([name, details]) => {
      const activityCard = document.createElement("div");
      activityCard.className = "activity-card";
      const spotsLeft = details.max_participants - details.participants.length;
      const participantsHTML = details.participants.length > 0
        ? `<div class="participants-section">
            <h5>Participants:</h5>
            <ul class="participants-list">
              ${details.participants.map((email) => `
                <li>
                  <span class="participant-email">${escapeHtml(email)}</span>
                  ${canManageActivity(name) ? `
                    <button class="delete-btn"
                      data-activity="${escapeHtml(name)}"
                      data-email="${escapeHtml(email)}"
                      aria-label="Unregister ${escapeHtml(email)}">Unregister</button>
                  ` : ""}
                </li>
              `).join("")}
            </ul>
          </div>`
        : "<p><em>No participants yet</em></p>";

      activityCard.innerHTML = `
        <h4>${escapeHtml(name)}</h4>
        <p>${escapeHtml(details.description)}</p>
        <p><strong>Schedule:</strong> ${escapeHtml(details.schedule)}</p>
        <p><strong>Availability:</strong> ${spotsLeft} spots left</p>
        <div class="participants-container">${participantsHTML}</div>
      `;
      activitiesList.appendChild(activityCard);
    });

    document.querySelectorAll(".delete-btn").forEach((button) => {
      button.addEventListener("click", handleUnregister);
    });
  }

  async function fetchActivities() {
    try {
      const activities = await apiFetch("/activities");
      renderActivities(activities);
    } catch (error) {
      activitiesList.innerHTML = "";
      const failure = document.createElement("p");
      failure.textContent = "Failed to load activities. Please try again later.";
      activitiesList.appendChild(failure);
      console.error("Error fetching activities:", error);
    }
  }

  async function loadOrganizers() {
    const organizers = await apiFetch("/staff/organizers");
    organizersList.innerHTML = "";
    if (organizers.length === 0) {
      organizersList.textContent = "No organizer accounts have been created.";
      return;
    }

    organizers.forEach((organizer) => {
      const card = document.createElement("div");
      card.className = "organizer-card";
      card.innerHTML = `
        <h5>${escapeHtml(organizer.username)}
          ${organizer.active ? "" : "(deactivated)"}</h5>
        ${organizer.active ? `
          <label>
            Assigned activities:
            <select multiple data-organizer="${escapeHtml(organizer.username)}">
              ${activityNames.map((name) => `
                <option value="${escapeHtml(name)}"
                  ${organizer.assignments.includes(name) ? "selected" : ""}>
                  ${escapeHtml(name)}
                </option>
              `).join("")}
            </select>
          </label>
          <div class="staff-actions">
            <button type="button" class="save-assignments"
              data-organizer="${escapeHtml(organizer.username)}">Save</button>
            <button type="button" class="deactivate-organizer"
              data-organizer="${escapeHtml(organizer.username)}">Deactivate</button>
          </div>
        ` : ""}
      `;
      organizersList.appendChild(card);
    });

    document.querySelectorAll(".save-assignments").forEach((button) => {
      button.addEventListener("click", saveAssignments);
    });
    document.querySelectorAll(".deactivate-organizer").forEach((button) => {
      button.addEventListener("click", deactivateOrganizer);
    });
  }

  function renderStaffState() {
    loginForm.classList.toggle("hidden", Boolean(currentStaff));
    staffSession.classList.toggle("hidden", !currentStaff);
    organizerAdmin.classList.toggle(
      "hidden",
      !currentStaff || currentStaff.role !== "admin"
    );
    if (currentStaff) {
      staffIdentity.textContent = `${currentStaff.username} (${currentStaff.role})`;
      fetchActivities();
      if (currentStaff.role === "admin") {
        loadOrganizers().catch((error) => {
          showMessage(staffMessage, error.message, "error");
        });
      }
    }
  }

  async function handleUnregister(event) {
    const button = event.currentTarget;
    const activity = button.dataset.activity;
    const email = button.dataset.email;
    try {
      const result = await apiFetch(
        `/activities/${encodeURIComponent(activity)}/unregister?email=${encodeURIComponent(email)}`,
        { method: "DELETE" }
      );
      showMessage(messageDiv, result.message, "success");
      await fetchActivities();
    } catch (error) {
      showMessage(messageDiv, error.message, "error");
    }
  }

  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const response = await fetch("/auth/token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: document.getElementById("staff-username").value,
          password: document.getElementById("staff-password").value,
        }),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.detail || "Sign in failed");
      }
      staffToken = result.access_token;
      currentStaff = await apiFetch("/auth/me");
      loginForm.reset();
      staffMessage.classList.add("hidden");
      renderStaffState();
    } catch (error) {
      staffToken = null;
      currentStaff = null;
      showMessage(staffMessage, error.message, "error");
    }
  });

  document.getElementById("staff-logout").addEventListener("click", () => {
    staffToken = null;
    currentStaff = null;
    organizersList.innerHTML = "";
    renderStaffState();
    fetchActivities();
  });

  organizerCreateForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const assignments = Array.from(organizerAssignments.selectedOptions)
      .map((option) => option.value);
    try {
      const result = await apiFetch("/staff/organizers", {
        method: "POST",
        body: JSON.stringify({
          username: document.getElementById("organizer-username").value,
          password: document.getElementById("organizer-password").value,
          assignments,
        }),
      });
      organizerCreateForm.reset();
      showMessage(staffMessage, `Created organizer ${result.username}`, "success");
      await loadOrganizers();
    } catch (error) {
      showMessage(staffMessage, error.message, "error");
    }
  });

  async function saveAssignments(event) {
    const username = event.currentTarget.dataset.organizer;
    const select = document.querySelector(
      `select[data-organizer="${CSS.escape(username)}"]`
    );
    const assignments = Array.from(select.selectedOptions)
      .map((option) => option.value);
    try {
      await apiFetch(`/staff/organizers/${encodeURIComponent(username)}`, {
        method: "PATCH",
        body: JSON.stringify({ assignments }),
      });
      showMessage(staffMessage, `Updated ${username}'s assignments`, "success");
      await loadOrganizers();
    } catch (error) {
      showMessage(staffMessage, error.message, "error");
    }
  }

  async function deactivateOrganizer(event) {
    const username = event.currentTarget.dataset.organizer;
    try {
      const result = await apiFetch(
        `/staff/organizers/${encodeURIComponent(username)}`,
        { method: "DELETE" }
      );
      showMessage(staffMessage, result.message, "success");
      await loadOrganizers();
    } catch (error) {
      showMessage(staffMessage, error.message, "error");
    }
  }

  signupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = document.getElementById("email").value;
    const activity = activitySelect.value;
    try {
      const result = await apiFetch(
        `/activities/${encodeURIComponent(activity)}/signup?email=${encodeURIComponent(email)}`,
        { method: "POST" }
      );
      showMessage(messageDiv, result.message, "success");
      signupForm.reset();
      await fetchActivities();
    } catch (error) {
      showMessage(messageDiv, error.message, "error");
    }
  });

  fetchActivities();
});
