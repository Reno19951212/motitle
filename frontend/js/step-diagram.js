// frontend/js/step-diagram.js — shared kind-agnostic step diagram.
// Renders backend-supplied `stages` array into a compact visual flow.
// Used by both the right-side queue panel (queue-panel.js) and the
// left-side dashboard file cards (index.html renderQueue()).
(function () {
  function renderStepDiagram(stages, stageIndex, stageState, pct) {
    if (!Array.isArray(stages) || stages.length === 0) return '';
    const allDone = stageState === 'done' && stageIndex != null && stageIndex >= stages.length - 1;
    return '<div class="step-diagram">' + stages.map((s, i) => {
      let cls, fill = '';
      if (allDone || i < stageIndex) cls = 'done';
      else if (i === stageIndex) {
        cls = (stageState === 'idle') ? 'pending' : 'active';
        if (cls === 'active' && pct != null) fill = `<span class="sd-fill" style="width:${Math.max(0, Math.min(100, pct))}%"></span>`;
      } else cls = 'pending';
      const mark = cls === 'done' ? '✓' : '';
      return `<span class="sd-step sd-${cls}" title="${(s.label || '').replace(/"/g, '&quot;')}">`
           + `<span class="sd-dot">${mark}${fill}</span>`
           + `<span class="sd-label">${(s.label || '')}</span></span>`
           + (i < stages.length - 1 ? '<span class="sd-arrow">→</span>' : '');
    }).join('') + '</div>';
  }
  window.renderStepDiagram = renderStepDiagram;
})();
