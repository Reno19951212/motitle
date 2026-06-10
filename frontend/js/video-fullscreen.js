/*
 * VideoFullscreen — keeps the SVG subtitle overlay visible in fullscreen.
 *
 * The native video control's fullscreen button fullscreens the bare <video>
 * element, which leaves the sibling subtitle overlay (<svg id="subtitleSvg">)
 * behind — so fullscreen playback shows no subtitle preview. The fix: when
 * the <video> becomes the fullscreen element, immediately swap fullscreen to
 * its CONTAINER (video + overlay together). The native controls keep working
 * and the overlay rides along.
 *
 * Usage: VideoFullscreen.wire(videoEl, containerEl)
 *   containerEl must be the positioned wrapper holding both the <video> and
 *   the subtitle <svg> (e.g. #videoArea on index, .rv-b-video on proofread).
 */
(function (global) {
  'use strict';

  function wire(video, container) {
    if (!video || !container) return;

    let containerFs = false;   // container is currently the fullscreen element
    let swapping = false;      // mid-swap — ignore the cascade of change events

    document.addEventListener('fullscreenchange', function () {
      if (swapping) return;
      const fs = document.fullscreenElement;

      if (fs !== video) {
        containerFs = fs === container;
        return;
      }

      // Native control fullscreened the bare <video>. If the container was
      // already fullscreen this is the user toggling OFF (nested fullscreen);
      // otherwise swap the fullscreen target to the container so the subtitle
      // overlay stays visible.
      swapping = true;
      const wantContainer = !containerFs;
      document.exitFullscreen()
        .then(function () {
          if (wantContainer) return container.requestFullscreen();
          // Nested case: first exit only popped back to the container.
          if (document.fullscreenElement) return document.exitFullscreen();
        })
        .catch(function () { /* user gesture expired or API refused — stay inline */ })
        .finally(function () {
          swapping = false;
          containerFs = document.fullscreenElement === container;
        });
    });

    // Safari: the native fullscreen button drives the presentation-mode API,
    // not the Fullscreen API — flip the video back inline and fullscreen the
    // container instead.
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
