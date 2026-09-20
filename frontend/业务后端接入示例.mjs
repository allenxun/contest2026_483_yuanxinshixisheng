// SPDX-License-Identifier: Apache-2.0
import { GimbalCloudClient } from './gimbal-cloud-client.mjs';

// APP token comes from the APP login flow. Do not put a gimbal credential or
// MiMo key in the frontend. The K7 exchanges its own provisioned credential for
// a short-lived device token and reports online state with heartbeat().
export function createBusinessApi(fetchImpl, appToken) {
  return new GimbalCloudClient({
    baseUrl: 'http://10.3.3.170:18085',
    fetchImpl,
    token: appToken
  });
}

// Call after VelaProvision.connectWifi() returned wifi_connected=true with a
// real IP. This updates the UI immediately, then reads the backend projection.
// It does not claim cloud connectivity before the K7 heartbeat is accepted.
export async function reconcileConnectedState(api, gimbalId, wifiResult, render, signal) {
  render({ wifiConnected: true, ip: wifiResult.ip, cloudConnected: false });
  const { data: status } = await api.getGimbalStatus(gimbalId, { signal });
  const cloudConnected = status.connectionStatus === 'online' && status.isStale === false;
  render({ cloudConnected, backendStatus: status.connectionStatus, backendStatusStale: status.isStale });
  return { wifiConnected: true, cloudConnected, status };
}

export async function submitAssessment(api, photos, capture, render, signal) {
  const key = crypto.randomUUID();
  const { data: accepted, requestId, meta } = await api.createAssessment({
    metadata: {
      photoVersion: '1',
      captureSessionId: capture.captureSessionId,
      consentEvidenceRef: capture.consentEvidenceRef
    },
    front: photos.front,
    left: photos.left,
    right: photos.right
  }, { key, signal });
  render({ assessmentStatus: accepted.status, taskId: accepted.taskId, photoVersion: accepted.photoVersion,
    requestId, replayed: meta.replayed });
  return { accepted, requestId, meta };
}
