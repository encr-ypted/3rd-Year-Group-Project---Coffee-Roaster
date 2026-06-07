import { ref } from 'vue';
import { createSensorFaultHold } from './sensorFaultHold';

const HOST = "coffee:8000"
const API_BASE = `http://${HOST}`;
const WS_URL = `ws://${HOST}/ws/telemetry`;

const PROFILE_DOTS = {
    light: 'bg-amber-400',
    medium: 'bg-amber-600',
    'medium-dark': 'bg-amber-800',
    dark: 'bg-amber-950',
};

const socket = ref(null);
const isConnected = ref(false);
const lastError = ref(null);
const roastProfiles = ref([]);
const profilesLoaded = ref(false);

const liveData = ref({
    timestamp: 0,
    temp: 20.0,
    targetTemp: 0.0,
    setpointTemp: 0.0,
    rampMidpointMin: 0,
    rampSteepness: 0,
    heaterPwm: 0,
    fanPwm: 0,
    state: 'IDLE',
    heaterHalted: false,
    canResume: false,
    sensorFault: null,
    testSpin: false,
});

const roastDataPoints = ref([]);
const roastPlan = ref(null);
/** Bean temp at roast start — locked from Pi telemetry for chart alignment. */
const roastStartTemp = ref(null);
const sensorFaultHold = createSensorFaultHold();

function lockRoastStartTemp(message) {
    if (message.start_temp != null && Number.isFinite(message.start_temp)) {
        return message.start_temp;
    }
    if (message.timestamp <= 1 && message.temp != null && Number.isFinite(message.temp)) {
        return message.temp;
    }
    return null;
}

function syncRoastPlanFromTelemetry(message) {
    if (!roastPlan.value || message.state === 'IDLE') {
        return;
    }

    const lockedStart = lockRoastStartTemp(message);
    if (roastStartTemp.value == null && lockedStart != null) {
        roastStartTemp.value = lockedStart;
    }

    roastPlan.value = {
        startTemp: roastStartTemp.value ?? roastPlan.value.startTemp,
        target: message.target ?? roastPlan.value.target,
        midpointMin: message.ramp_midpoint_min ?? roastPlan.value.midpointMin,
        steepness: message.ramp_steepness ?? roastPlan.value.steepness,
        locked: roastStartTemp.value != null,
    };
}

const sendJson = (payload) => {
    if (!socket.value || socket.value.readyState !== WebSocket.OPEN) return false;
    socket.value.send(JSON.stringify(payload));
    return true;
};

function mapProfiles(rows) {
    return rows.map((p) => ({
        id: p.id,
        name: p.name,
        desc: p.desc || '',
        temp: p.target_c,
        target_c: p.target_c,
        rampMid: p.ramp_midpoint_min,
        rampK: p.ramp_steepness,
        dot: PROFILE_DOTS[p.id] || 'bg-amber-600',
    }));
}

export const useCoffeeRoaster = () => {
    const loadProfiles = async () => {
        try {
            const res = await fetch(`${API_BASE}/api/profiles`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            roastProfiles.value = mapProfiles(data.profiles || []);
            profilesLoaded.value = true;
        } catch (e) {
            console.error('Failed to load roast profiles:', e);
            lastError.value = 'Could not load roast profiles from Pi (GET /api/profiles)';
            profilesLoaded.value = false;
        }
    };

    const connect = () => {
        if (socket.value && socket.value.readyState === WebSocket.OPEN) return;

        socket.value = new WebSocket(WS_URL);

        socket.value.onopen = () => {
            isConnected.value = true;
            lastError.value = null;
            getSystemState();
        };

        socket.value.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);

                if (message.type === 'telemetry') {
                    liveData.value = {
                        ...liveData.value,
                        timestamp: message.timestamp,
                        temp: message.temp,
                        targetTemp: message.target,
                        setpointTemp: message.setpoint ?? message.target,
                        rampMidpointMin:
                            message.ramp_midpoint_min ?? liveData.value.rampMidpointMin,
                        rampSteepness:
                            message.ramp_steepness ?? liveData.value.rampSteepness,
                        heaterPwm: message.heater_pwm,
                        fanPwm: message.fan_pwm,
                        state: message.state,
                        heaterHalted: message.heater_halted ?? liveData.value.heaterHalted,
                        canResume: message.can_resume ?? false,
                        testSpin:
                            message.test_spin !== undefined
                                ? message.test_spin
                                : liveData.value.testSpin,
                    };
                    sensorFaultHold.apply(
                        (v) => { liveData.value.sensorFault = v },
                        message.sensor_fault ?? null,
                    );

                    if (message.state === 'IDLE') {
                        roastStartTemp.value = null;
                    } else {
                        syncRoastPlanFromTelemetry(message);
                    }

                    if (message.state !== 'IDLE' && message.temp != null) {
                        roastDataPoints.value.push({ ...liveData.value });
                    }
                } else if (message.type === 'system_state') {
                    liveData.value.state = message.state;
                } else if (message.type === 'heater_status') {
                    liveData.value.heaterHalted = message.heater_halted ?? false;
                } else if (message.type === 'roast_action') {
                    if (message.test_spin !== undefined) {
                        liveData.value.testSpin = message.test_spin;
                    }
                    if (message.fan_pwm !== undefined) {
                        liveData.value.fanPwm = message.fan_pwm;
                    }
                    if (message.state !== undefined) {
                        liveData.value.state = message.state;
                    }
                    if (
                        message.action === 'TEST_SPIN'
                        || message.action === 'TEST_SPIN_START'
                        || message.action === 'TEST_SPIN_STOP'
                    ) {
                        if (!message.ok) {
                            lastError.value =
                                'Test spin only works when the roaster is idle';
                        } else {
                            lastError.value = null;
                        }
                    }
                } else if (message.type === 'error') {
                    lastError.value = message.msg;
                }
            } catch (e) {
                console.error('Error parsing WebSocket message:', e);
            }
        };

        socket.value.onclose = () => {
            isConnected.value = false;
            socket.value = null;
            setTimeout(connect, 3000);
        };

        socket.value.onerror = () => {
            isConnected.value = false;
        };
    };

    const disconnect = () => {
        socket.value?.close();
    };

    const setRoastPlanFromProfile = (profile) => {
        if (!profile) {
            roastPlan.value = null;
            return;
        }
        roastPlan.value = {
            startTemp: liveData.value.temp ?? 20,
            target: profile.target_c,
            midpointMin: profile.rampMid ?? 2,
            steepness: profile.rampK ?? 1,
        };
    };

    const startRoast = (profileId) => {
        if (!isConnected.value) return;
        roastDataPoints.value = [];
        roastStartTemp.value = null;
        const profile = roastProfiles.value.find((p) => p.id === profileId);
        setRoastPlanFromProfile(profile);
        sendJson({ action: 'START_ROAST', profile_id: profileId });
    };

    const stopRoast = () => {
        if (!isConnected.value) return;
        sendJson({ action: 'STOP_ROAST' });
    };

    const resumeRoast = () => {
        if (!isConnected.value) return;
        sendJson({ action: 'RESUME_ROAST' });
    };

    const finishRoast = () => {
        if (!isConnected.value) return;
        sendJson({ action: 'FINISH_ROAST' });
    };

    const emergencyStop = () => {
        if (!isConnected.value) return;
        sendJson({ action: 'E_STOP' });
    };

    const toggleTestSpin = () => {
        if (!isConnected.value) return;
        sendJson({
            action: 'TEST_SPIN',
            enable: !liveData.value.testSpin,
        });
    };

    const getSystemState = () => {
        sendJson({ action: 'GET_STATE' });
    };

    return {
        connect,
        loadProfiles,
        isConnected,
        lastError,
        liveData,
        roastProfiles,
        profilesLoaded,
        roastDataPoints,
        roastPlan,
        setRoastPlanFromProfile,
        startRoast,
        stopRoast,
        resumeRoast,
        finishRoast,
        emergencyStop,
        toggleTestSpin,
        getSystemState,
    };
};
