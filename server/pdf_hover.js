// Document-level Acrobat JavaScript. The builder prepends folioHoverData/Pages.
// No annotation overlays, mouse handlers, network calls, or clipboard access.
var folioHoverDoc = this;
var folioHoverTimer = null;
var folioHoverCurrent = -1;
var folioHoverLayers = [];
var folioHoverPaused = false;
var folioHoverByPage = {};

function folioHoverClear() {
    if (folioHoverCurrent >= 0) {
        folioHoverLayers[folioHoverCurrent].state = false;
        folioHoverCurrent = -1;
    }
}

function folioHoverStop() {
    if (folioHoverTimer !== null) {
        try { app.clearInterval(folioHoverTimer); } catch (e) {}
        folioHoverTimer = null;
    }
    try { folioHoverClear(); } catch (e) { folioHoverCurrent = -1; }
}

function folioHoverContains(rect, x, y) {
    return x >= rect[0] && x <= rect[2] && y >= rect[1] && y <= rect[3];
}

function folioHoverTick() {
    if (folioHoverPaused) { return; }
    try {
        var page = folioHoverDoc.pageNum;
        var x = folioHoverDoc.mouseX;
        var y = folioHoverDoc.mouseY;
        var target = -1;
        if (typeof page === "number" && page === Math.floor(page) &&
            page >= 0 && page < folioHoverPages.length &&
            typeof x === "number" && typeof y === "number" &&
            isFinite(x) && isFinite(y) && folioHoverContains(folioHoverPages[page], x, y)) {
            var candidates = folioHoverByPage[page] || [];
            for (var k = 0; k < candidates.length && target < 0; k++) {
                var i = candidates[k];
                var rects = folioHoverData[i].rects;
                for (var j = 0; j < rects.length; j++) {
                    if (folioHoverContains(rects[j], x, y)) { target = i; break; }
                }
            }
        }
        if (target === folioHoverCurrent) { return; }
        folioHoverClear();
        if (target >= 0) {
            folioHoverLayers[target].state = true;
            folioHoverCurrent = target;
        }
    } catch (e) {
        folioHoverStop();
    }
}

function folioHoverPause() {
    folioHoverPaused = true;
    folioHoverClear();
}

function folioHoverResume() {
    folioHoverPaused = false;
}

function folioHoverInit() {
    try {
        var layers = folioHoverDoc.getOCGs();
        if (!layers) { return; }
        var byName = {};
        for (var j = 0; j < layers.length; j++) { byName[layers[j].name] = layers[j]; }
        for (var i = 0; i < folioHoverData.length; i++) {
            var found = byName[folioHoverData[i].name];
            if (!found) { folioHoverLayers = []; return; }
            folioHoverLayers.push(found);
            found.state = false;
            var page = folioHoverData[i].page;
            if (!folioHoverByPage[page]) { folioHoverByPage[page] = []; }
            folioHoverByPage[page].push(i);
        }
        // Keep the handle at document scope so Acrobat does not collect it.
        folioHoverTimer = app.setInterval("folioHoverTick()", 100);
    } catch (e) {
        folioHoverStop();
    }
}

folioHoverInit();
