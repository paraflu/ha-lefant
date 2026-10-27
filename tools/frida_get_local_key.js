// Lefant M1 — read the Tuya local key from the running app, without modifying it.
//
// The local key is a per-device cloud credential delivered after login; it lives
// in the SDK's DeviceBean. This hooks the public getter and returns the ORIGINAL
// value, so the app behaves exactly as before.
//
// Run:  frida -U -p <pid> -l frida_get_local_key.js
//   (prefer attach to the running app over `-f`: spawning through Frida on a
//    translated emulator is slower and losing the session loses the hook.)
// Then log in, open the vacuum control screen, and watch your own terminal.
//
// Note: `ov.returnType.className` is 'java.lang.String'; `ov.returnType.type`
// is a Type object, so String(returnType) yields 'Ljava/lang/String;'. Getting
// this check wrong silently hooks nothing and prints nothing.

var TARGETS = [
    'com.thingclips.smart.sdk.bean.DeviceBean',
    'com.thingclips.smart.android.device.bean.DeviceBean'
];

var hooked = new Set();
var reported = new Set();

function report(where, devId, key) {
    // Print once per (where, devId, key) so the console stays readable.
    var sig = where + '|' + devId + '|' + key;
    if (reported.has(sig)) return;
    reported.add(sig);
    console.log('[M1] ' + where);
    console.log('[M1]   devId    = ' + devId);
    console.log('[M1]   localKey = ' + key + '   (len=' + (key ? key.length : 0) + ')');
}

function hookOverloads(name, Klass) {
    var getter;
    try {
        getter = Klass.getLocalKey;
    } catch (e) {
        return 0;
    }
    var overloads = getter.overloads || [];
    if (!overloads.length) return 0;

    var added = 0;
    overloads.forEach(function (ov) {
        // Only the plain String getter is interesting; skip odd signatures so
        // the fallback scan does not hook unrelated SDK plumbing.
        // NB: returnType.className is 'java.lang.String'; returnType.type is a
        // Type object, so String(returnType) gives 'Ljava/lang/String;'.
        if (ov.argumentTypes.length !== 0) return;
        if (ov.returnType.className !== 'java.lang.String') return;
        if (hooked.has(name + '/0')) return;
        ov.implementation = function () {
            var key = ov.call(this);          // original implementation
            var devId = '(unavailable)';
            try { devId = this.getDevId(); } catch (e) {}
            report(name, devId, key);
            return key;                        // preserve behaviour
        };
        hooked.add(name + '/' + ov.argumentTypes.length);
        added += 1;
    });
    if (added) console.log('[M1] hooked ' + name + '.getLocalKey');
    return added;
}

function isInterface(Klass) {
    try { return Klass.class.isInterface(); } catch (e) { return false; }
}

function tryInstall() {
    var total = 0;
    TARGETS.forEach(function (name) {
        try { total += hookOverloads(name, Java.use(name)); } catch (e) {}
    });
    // Fallback: any loaded thingclips class exposing getLocalKey.
    if (total === 0) {
        Java.enumerateLoadedClassesSync().forEach(function (name) {
            if (name.indexOf('thingclips') === -1) return;
            if (hooked.has(name + '/0')) return;
            try {
                var K = Java.use(name);
                if (isInterface(K)) return;
                total += hookOverloads(name, K);
            } catch (e) {}
        });
    }
    return total;
}

Java.perform(function () {
    // The SDK classes load after the UI appears, so retry for a while.
    var attempts = 0;
    var timer = setInterval(function () {
        attempts += 1;
        var n = 0;
        try { n = tryInstall(); } catch (e) { console.log('[M1] install error: ' + e); }
        if (n > 0 && attempts > 4) {
            clearInterval(timer);
            console.log('[M1] hook ready — open the vacuum control screen.');
        }
        // Silence is ambiguous: say so instead of looking dead.
        if (attempts % 10 === 0 && hooked.size === 0) {
            console.log('[M1] ancora nessun hook (tentativo ' + attempts +
                        ') — l\'app e\' al login?');
        }
        if (attempts > 60) clearInterval(timer);   // ~2 min, then stop
    }, 2000);
});
