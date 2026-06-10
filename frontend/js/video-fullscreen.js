/*
 * VideoFullscreen — keeps the SVG subtitle overlay visible in fullscreen.
 *
 * The native video control's fullscreen button fullscreens the bare <video>
 * element, which leaves the sibling subtitle overlay (<svg id="subtitleSvg">)
 * behind. A JS exit-and-reenter swap does NOT work in Chrome: the user's
 * click activation is consumed by the first fullscreen request, so the
 * follow-up container.requestFullscreen() is rejected and the player bounces
 * back inline. So instead: hide the native fullscreen button
 * (controlslist="nofullscreen") and provide our own button that fullscreens
 * the CONTAINER (video + overlay together) in one user gesture.
 *
 * Usage: VideoFullscreen.wire(videoEl, containerEl)
 *   containerEl must be the positioned wrapper holding both the <video> and
 *   the subtitle <svg> (e.g. #videoArea on index, .rv-b-video on proofread).
 */
(function (global) {
  'use strict';

  const ICON_EXPAND =
    '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M6 2H2v4M10 2h4v4M6 14H2v-4M10 14h4v-4"/></svg>';
  const ICON_COLLAPSE =
    '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M2 6h4V2M14 6h-4V2M2 10h4v4M14 10h-4v4"/></svg>';

  let stylesInjected = false;
  function injectStyles() {
    if (stylesInjected) return;
    stylesInjected = true;
    const css =
      '.vfs-btn{position:absolute;top:10px;right:10px;z-index:5;width:34px;height:34px;' +
      'display:none;align-items:center;justify-content:center;cursor:pointer;' +
      'background:rgba(0,0,0,.55);color:#fff;border:1px solid rgba(255,255,255,.25);' +
      'border-radius:8px;opacity:.65;transition:opacity .15s ease;padding:0;}' +
      '.vfs-btn:hover,.vfs-btn:focus-visible{opacity:1;}' +
      '.vfs-btn.vfs-visible{display:flex;}';
    const el = document.createElement('style');
    el.textContent = css;
    document.head.appendChild(el);
  }

  function wire(video, container) {
    if (!video || !container) return;
    injectStyles();

    // Hide the native fullscreen button — it can only fullscreen the bare
    // <video>, which loses the subtitle overlay (also disables Chrome's
    // double-click-to-fullscreen on the video).
    const cl = (video.getAttribute('controlslist') || '').trim();
    if (!/\bnofullscreen\b/.test(cl)) {
      video.setAttribute('controlslist', (cl + ' nofullscreen').trim());
    }

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'vfs-btn';
    btn.title = '全螢幕（連字幕預覽）';
    btn.setAttribute('aria-label', '全螢幕');
    btn.innerHTML = ICON_EXPAND;
    container.appendChild(btn);

    btn.addEventListener('click', function () {
      if (document.fullscreenElement === container) {
        document.exitFullscreen().catch(function () {});
      } else if (container.requestFullscreen) {
        container.requestFullscreen().catch(function () {});
      } else if (container.webkitRequestFullscreen) {
        container.webkitRequestFullscreen();
      }
    });

    document.addEventListener('fullscreenchange', function () {
      const fs = document.fullscreenElement === container;
      btn.innerHTML = fs ? ICON_COLLAPSE : ICON_EXPAND;
      btn.title = fs ? '退出全螢幕' : '全螢幕（連字幕預覽）';
    });

    // The button only makes sense once a video is actually loaded (both pages
    // start with the <video> hidden behind a placeholder).
    video.addEventListener('loadeddata', function () { btn.classList.add('vfs-visible'); });
    video.addEventListener('emptied', function () { btn.classList.remove('vfs-visible'); });

    // Safari: the native fullscreen button drives the presentation-mode API —
    // flip the video back inline and fullscreen the container instead.
    if (typeof video.webkitSetPresentationMode === 'function') {
      video.addEventListener('webkitpresentationmodechanged', function () {
        if (video.webkitPresentationMode !== 'fullscreen') return;
        if (document.fullscreenElement === container) return;
        video.webkitSetPresentationMode('inline');
        const req = container.requestFullscreen || container.webkitRequestFullscreen;
        if (req) {
          try { req.call(container); } catch (e) { /* stay inline */ }
        }
      });
    }
  }

  global.VideoFullscreen = { wire: wire };
})(window);
