// Recipient page for Secure Share links: /static/shared.html#<token>.
// The token lives in the URL fragment, so it is never sent in a request line
// or written to server access logs; it is POSTed only to the access endpoint.
(function () {
  'use strict';
  var token = decodeURIComponent((window.location.hash || '').slice(1));
  var btn = document.getElementById('download');
  var msg = document.getElementById('msg');
  var pwRow = document.getElementById('password-row');
  var pw = document.getElementById('password');

  function show(text, ok) {
    msg.textContent = text;
    msg.className = 'msg ' + (ok ? 'ok' : 'err');
  }

  function filenameFrom(res) {
    var cd = res.headers.get('Content-Disposition') || '';
    var star = /filename\*=UTF-8''([^;]+)/i.exec(cd);
    if (star) return decodeURIComponent(star[1]);
    var plain = /filename="?([^";]+)"?/i.exec(cd);
    return plain ? plain[1] : 'download';
  }

  if (!token) {
    btn.disabled = true;
    show('This link is incomplete. Ask the sender for the full link.');
    return;
  }

  btn.addEventListener('click', function () {
    btn.disabled = true;
    show('', true);
    fetch('/api/file-share/access/' + encodeURIComponent(token), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pwRow.hidden ? null : pw.value })
    }).then(function (res) {
      if (res.ok) {
        return res.blob().then(function (blob) {
          var a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = filenameFrom(res);
          document.body.appendChild(a);
          a.click();
          a.remove();
          show('Download started.', true);
        });
      }
      return res.json().catch(function () { return {}; }).then(function (body) {
        if (res.status === 403) {
          pwRow.hidden = false;
          pw.focus();
          show(pw.value ? 'Incorrect password.' : 'This file is password protected.');
        } else if (res.status === 429) {
          show('Too many attempts. Wait a minute and try again.');
        } else {
          show(body.detail || 'The file could not be downloaded.');
        }
      });
    }).catch(function () {
      show('Network error. Try again.');
    }).then(function () {
      btn.disabled = false;
    });
  });
})();
