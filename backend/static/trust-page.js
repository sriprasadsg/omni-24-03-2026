// Public trust page logic. Served as a same-origin file because the page's
// CSP (script-src 'self') blocks inline scripts.
(function () {
  'use strict';

  function getSlug() {
    var parts = window.location.pathname.split('/').filter(Boolean);
    return parts.length >= 2 ? decodeURIComponent(parts[1]) : '';
  }

  var slug = getSlug();
  var contactEmail = '';

  var loadingState = document.getElementById('loading-state');
  var notFoundState = document.getElementById('not-found-state');
  var pageContent = document.getElementById('page-content');

  function show(el) { el.classList.remove('hidden'); }
  function hide(el) { el.classList.add('hidden'); }

  function renderProfile(profile) {
    contactEmail = profile.contact_email || '';

    document.getElementById('company-name').textContent = profile.company_name || '';
    document.getElementById('company-description').textContent = profile.description || '';
    document.getElementById('contact-email').textContent = contactEmail;

    var frameworks = profile.compliance_frameworks || [];
    if (frameworks.length > 0) {
      var row = document.getElementById('framework-row');
      row.innerHTML = '';
      frameworks.forEach(function (fw) {
        var badge = document.createElement('span');
        badge.className = 'framework-badge';
        badge.textContent = fw;
        row.appendChild(badge);
      });
      show(document.getElementById('frameworks-card'));
    }

    var publicDocs = profile.public_documents || [];
    var publicList = document.getElementById('public-doc-list');
    if (publicDocs.length > 0) {
      publicDocs.forEach(function (doc) {
        var li = document.createElement('li');
        li.className = 'doc-row';
        var name = document.createElement('span');
        name.className = 'doc-name';
        name.textContent = doc.name || '';
        var link = document.createElement('a');
        link.className = 'doc-link';
        link.href = doc.url || '#';
        link.textContent = 'Download';
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        li.appendChild(name);
        li.appendChild(link);
        publicList.appendChild(li);
      });
    } else {
      document.getElementById('public-docs-empty-body').textContent =
        'This company hasn\'t published any public compliance documents. Check back later, or contact them directly at ' + contactEmail + '.';
      show(document.getElementById('public-docs-empty'));
    }

    var privateDocs = profile.private_documents || [];
    if (privateDocs.length > 0) {
      var restrictedList = document.getElementById('restricted-doc-list');
      privateDocs.forEach(function (doc) {
        var li = document.createElement('li');
        li.className = 'doc-row';

        var name = document.createElement('span');
        name.className = 'doc-name';
        name.textContent = doc.name || '';

        var right = document.createElement('span');
        var label = document.createElement('span');
        label.className = 'doc-restricted-label';
        label.textContent = 'NDA Required';
        right.appendChild(label);

        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn';
        btn.textContent = 'Request Access';
        btn.addEventListener('click', function () {
          show(document.getElementById('request-card'));
          document.getElementById('request-card').scrollIntoView({ behavior: 'smooth' });
        });
        right.appendChild(btn);

        li.appendChild(name);
        li.appendChild(right);
        restrictedList.appendChild(li);
      });
      show(document.getElementById('restricted-card'));
    }

    hide(loadingState);
    show(pageContent);
  }

  function showNotFound() {
    hide(loadingState);
    show(notFoundState);
  }

  function showBanner(message) {
    var banner = document.getElementById('form-banner');
    banner.textContent = message;
    banner.classList.add('show');
  }

  function hideBanner() {
    var banner = document.getElementById('form-banner');
    banner.classList.remove('show');
    banner.textContent = '';
  }

  function isValidEmail(value) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  }

  function initForm() {
    var form = document.getElementById('access-request-form');
    var emailInput = document.getElementById('req-email');
    var consentInput = document.getElementById('req-consent');
    var emailError = document.getElementById('email-error');
    var consentError = document.getElementById('consent-error');

    form.addEventListener('submit', function (evt) {
      evt.preventDefault();
      hideBanner();
      emailError.classList.remove('show');
      consentError.classList.remove('show');

      var email = emailInput.value.trim();
      var consent = consentInput.checked;

      var valid = true;
      if (!isValidEmail(email)) {
        emailError.classList.add('show');
        valid = false;
      }
      if (!consent) {
        consentError.classList.add('show');
        valid = false;
      }
      if (!valid) return;

      var payload = {
        requester_email: email,
        company: document.getElementById('req-company').value.trim(),
        reason: document.getElementById('req-reason').value.trim(),
        consent: true
      };

      fetch('/api/public/trust/' + encodeURIComponent(slug) + '/requests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(function (resp) {
        if (resp.status === 200 || resp.status === 201) {
          form.classList.add('hidden');
          var successEl = document.getElementById('success-message');
          successEl.textContent = 'Request received. ' + (document.getElementById('company-name').textContent || 'The company') + ' will review your request and follow up at the email you provided.';
          successEl.classList.add('show');
        } else if (resp.status === 429) {
          showBanner('Too many requests from your network. Please wait a minute and try again.');
        } else {
          showBanner('Something went wrong submitting your request. Please try again, or email ' + contactEmail + ' directly.');
        }
      }).catch(function () {
        showBanner('Something went wrong submitting your request. Please try again, or email ' + contactEmail + ' directly.');
      });
    });
  }

  function init() {
    if (!slug) {
      showNotFound();
      return;
    }
    initForm();
    fetch('/api/public/trust/' + encodeURIComponent(slug))
      .then(function (resp) {
        if (resp.status === 404) {
          showNotFound();
          return null;
        }
        if (!resp.ok) {
          throw new Error('Request failed');
        }
        return resp.json();
      })
      .then(function (profile) {
        if (profile) renderProfile(profile);
      })
      .catch(function () {
        showNotFound();
      });
  }

  init();
})();
