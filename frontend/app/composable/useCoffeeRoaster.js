import { ref } from 'vue';

const API_BASE = 'http://10.115.50.98:8000';
const WS_URL = 'ws://10.115.50.98:8000/ws/telemetry';

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
    ror: 0.0,
    heaterPwm: 0,
    fanPwm: 0,
    state: 'IDLE',
    heaterHalted: false,
});

const roastDataPoints = ref([]);

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
                        ror: message.ror,
                        heaterPwm: message.heater_pwm,
                        fanPwm: message.fan_pwm,
                        state: message.state,
                        heaterHalted: message.heater_halted ?? liveData.value.heaterHalted,
                    };

                    if (message.state !== 'IDLE') {
                        roastDataPoints.value.push({ ...liveData.value });
                    }
                } else if (message.type === 'system_state') {
                    liveData.value.state = message.state;
                } else if (message.type === 'heater_status') {
                    liveData.value.heaterHalted = message.heater_halted ?? false;
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

    const startRoast = (profileId) => {
        if (!isConnected.value) return;
        roastDataPoints.value = [];
        sendJson({ action: 'START_ROAST', profile_id: profileId });
    };

    const stopRoast = () => {
        if (!isConnected.value) return;
        sendJson({ action: 'STOP_ROAST' });
    };

    const emergencyStop = () => {
        if (!isConnected.value) return;
        sendJson({ action: 'E_STOP' });
    };

    const clearHeaterHalt = () => {
        if (!isConnected.value) return;
        sendJson({ action: 'HEATER_CLEAR_HALT' });
    };

    const getSystemState = () => {
        sendJson({ action: 'GET_STATE' });
    };

    return {
        connect,
        disconnect,
        loadProfiles,
        isConnected,
        lastError,
        liveData,
        roastProfiles,
        profilesLoaded,
        roastDataPoints,
        startRoast,
        stopRoast,
        emergencyStop,
        clearHeaterHalt,
        getSystemState,
    };
};
