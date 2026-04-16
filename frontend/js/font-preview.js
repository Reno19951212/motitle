/**
 * FontPreview — synchronises the #subtitleSvgText overlay with the active
 * Profile's font config. Uses Socket.IO for real-time updates.
 *
 * Usage:
 *   FontPreview.init(socketOrNull)   // call on page init; socket may be null
 *   FontPreview.updateText(text)     // call from timeupdate handler
 */
const FontPreview = (() => {
  const _apiBase = (typeof API_BASE !== 'undefined' ? API_BASE : 'http://localhost:5001');
  let _svgEl = null;
  let _textEl = null;
  let _listenerRegistered = false;

  function applyFontConfig(font) {
    if (!font) return;
    const size = Number(font.size) || 48;
    const strokeWidth = (font.outline_width != null ? Number(font.outline_width) : 2) * 2;
    const svgHeight = size + strokeWidth + 10;

    const root = document.documentElement;
    root.style.setProperty('--preview-font-family', font.family || 'Noto Sans TC');
    root.style.setProperty('--preview-font-size', size + 'px');
    root.style.setProperty('--preview-font-color', font.color || '#FFFFFF');
    root.style.setProperty('--preview-outline-color', font.outline_color || '#000000');
    root.style.setProperty('--preview-outline-width', strokeWidth + 'px');
    const mb = font.margin_bottom != null ? Number(font.margin_bottom) : 40;
    root.style.setProperty('--preview-margin-bottom', mb + 'px');

    if (_svgEl) {
      _svgEl.setAttribute('height', svgHeight);
    }
    if (_textEl) {
      _textEl.setAttribute('y', size + strokeWidth);
      _textEl.setAttribute('font-family', font.family || 'Noto Sans TC');
      _textEl.setAttribute('font-size', size);
      _textEl.setAttribute('fill', font.color || '#FFFFFF');
      _textEl.setAttribute('stroke', font.outline_color || '#000000');
      _textEl.setAttribute('stroke-width', strokeWidth);
    }
  }

  function init(socketOrNull) {
    if (!_svgEl || !_svgEl.isConnected) {
      _svgEl = document.getElementById('subtitleSvg');
      _textEl = document.getElementById('subtitleSvgText');

      fetch(`${_apiBase}/api/profiles/active`)
        .then(r => r.ok ? r.json() : null)
        .then(data => {
          if (data && data.profile && data.profile.font) applyFontConfig(data.profile.font);
        })
        .catch((err) => { console.warn('[FontPreview] Failed to fetch active profile:', err); });
    }

    const sock = socketOrNull || (typeof io !== 'undefined' ? io(_apiBase) : null);
    if (sock && !_listenerRegistered) {
      _listenerRegistered = true;
      sock.on('profile_updated', (data) => {
        if (data && data.font) applyFontConfig(data.font);
      });
    }
  }

  function updateText(text) {
    if (!_textEl) return;
    _textEl.textContent = text || '';
    _textEl.style.opacity = (text && text.trim()) ? '1' : '0';
  }

  return { init, updateText };
})();
