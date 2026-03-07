/**
 * KCH UAT Test Runner — client-side helpers
 */

// Show/hide failure fields based on selected outcome
function handleOutcomeChange(value, scriptId) {
  const failureFields = document.getElementById(`failure-fields-${scriptId}`);
  if (!failureFields) return;
  const show = value === 'Fail' || value === 'Blocked';
  failureFields.style.display = show ? 'block' : 'none';

  // Mark required only when visible
  const fc = document.getElementById(`failure_category_${scriptId}`);
  const hap = document.getElementById(`happened_${scriptId}`);
  if (fc) fc.required = show;
  if (hap) hap.required = show;
}

// Set sidebar item as active and remove active from others
function setActive(scriptId) {
  document.querySelectorAll('.script-item').forEach(el => {
    el.classList.toggle('active', el.dataset.scriptId === scriptId);
  });
}

// Update a single sidebar item's outcome badge and class
function updateSidebarItem(scriptId, outcome) {
  const item = document.querySelector(`.script-item[data-script-id="${scriptId}"]`);
  if (!item) return;

  // Remove all outcome classes
  item.className = item.className.replace(/\boutcome-\S+/g, '').trim();

  const badge = item.querySelector('.script-outcome-badge');
  let cls = 'outcome-none';
  let icon = '○';

  if (outcome === 'Pass')       { cls = 'outcome-pass';    icon = '✓'; }
  else if (outcome === 'Fail')  { cls = 'outcome-fail';    icon = '✗'; }
  else if (outcome === 'Blocked') { cls = 'outcome-blocked'; icon = '⊘'; }
  else if (outcome === 'Not Tested') { cls = 'outcome-nt'; icon = '–'; }

  item.classList.add(cls);
  if (badge) badge.textContent = icon;
}

// Filter sidebar script list by search term
function filterScripts(term) {
  const lower = term.toLowerCase();
  document.querySelectorAll('.script-item').forEach(el => {
    const title = (el.dataset.title || '').toLowerCase();
    const id = (el.dataset.scriptId || '').toLowerCase();
    el.style.display = (title.includes(lower) || id.includes(lower)) ? '' : 'none';
  });
}

// NHS email validation on blur
document.addEventListener('DOMContentLoaded', () => {
  const emailInput = document.getElementById('tester_email');
  if (emailInput) {
    emailInput.addEventListener('blur', () => {
      const val = emailInput.value.trim().toLowerCase();
      let hint = emailInput.parentElement.querySelector('.field-error.js-hint');
      if (!hint) {
        hint = document.createElement('p');
        hint.className = 'field-error js-hint';
        emailInput.parentElement.appendChild(hint);
      }
      if (val && !val.endsWith('@nhs.net')) {
        hint.textContent = 'Email must end with @nhs.net';
      } else {
        hint.textContent = '';
      }
    });
  }

});
