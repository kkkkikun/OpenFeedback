/* Admin UI behaviour: status changes and notes post to the admin API. */
(function () {
  'use strict';

  var meta = document.querySelector('meta[name="csrf-token"]');
  var csrfToken = meta ? meta.getAttribute('content') : '';

  function api(path, method, body) {
    return fetch(path, {
      method: method,
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken
      },
      credentials: 'same-origin',
      body: body ? JSON.stringify(body) : undefined
    }).then(function (res) {
      if (!res.ok) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          throw new Error(data.detail || ('请求失败 ' + res.status));
        });
      }
      return res.json();
    });
  }

  function flash(text, isError) {
    var box = document.createElement('div');
    box.className = 'alert ' + (isError ? 'alert-error' : 'alert');
    box.textContent = text;
    box.style.marginBottom = '12px';
    var anchor = document.querySelector('.detail');
    if (anchor && anchor.parentNode) { anchor.parentNode.insertBefore(box, anchor); }
    setTimeout(function () { box.remove(); }, 4000);
  }

  document.querySelectorAll('.status-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var id = btn.getAttribute('data-id');
      var status = btn.getAttribute('data-status');
      btn.disabled = true;
      api('/api/v1/admin/feedback/' + id, 'PATCH', { status: status })
        .then(function () {
          document.querySelectorAll('.status-btn').forEach(function (b) {
            b.classList.toggle('is-active', b === btn);
          });
          flash('状态已更新为 ' + status);
        })
        .catch(function (err) { flash(err.message, true); })
        .finally(function () { btn.disabled = false; });
    });
  });

  var noteForm = document.getElementById('note-form');
  if (noteForm) {
    noteForm.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var box = document.getElementById('note-content');
      var text = box.value.trim();
      if (!text) { return; }
      var id = noteForm.getAttribute('data-id');
      api('/api/v1/admin/feedback/' + id + '/notes', 'POST', { content: text })
        .then(function () {
          box.value = '';
          flash('备注已添加');
          setTimeout(function () { window.location.reload(); }, 600);
        })
        .catch(function (err) { flash(err.message, true); });
    });
  }
})();
