// SPDX-License-Identifier: Apache-2.0
import { VelaOnlineSpeechAdapter } from './整机联网语音适配器.mjs';
import { SpeechHttpClient } from './speech-http-client.mjs';

// speechBaseUrl points to the team's host/backend bridge. The bridge owns the
// MiMo credential; the App receives neither that credential nor an option to
// inject it into SpeechHttpClient.
export function createWholeDeviceClient(uni, {
  speechBaseUrl,
  render,
  reportDeviceOnline,
  probeDeviceInternet = async () => false,
  fetchImpl = globalThis.fetch,
  provision = null
}) {
  const speech = new SpeechHttpClient(speechBaseUrl, { fetchImpl });
  const health = () => speech.health();
  return new VelaOnlineSpeechAdapter(uni, {
    onState: render,
    // Must prove the current K7 route; App/phone health requests cannot do so.
    internetProbe: probeDeviceInternet,
    reportOnline: reportDeviceOnline,
    cloudProbe: async () => {
      const state = await health();
      return state.ready && state.asr && state.tts;
    },
    speechClient: {
      asr: (wav16kMono, options) => speech.asr(wav16kMono, options),
      tts: (text, options) => speech.tts(text, options)
    },
    provision
  });
}

export async function provisionAndEnableSpeech(client, {
  deviceId, ssid_b64, password, clearPasswordInput
}) {
  await client.open(deviceId);
  await client.scan();
  client.selectNetwork(ssid_b64);
  return client.connectSelected(password, clearPasswordInput);
}
