// mobile/lib/share.js
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import { API_URL } from '../constants';
import { getToken } from './session';

/**
 * Downloads the day's workout as a Zwift .zwo file and opens the share sheet,
 * so it can go to the Mac by AirDrop (or into Files, Mail, ...).
 */
export async function shareWorkout(journeyId, day) {
  if (!(await Sharing.isAvailableAsync())) throw new Error('Sharing is not available on this device.');
  const dir = `${FileSystem.cacheDirectory}zwo/`;
  await FileSystem.makeDirectoryAsync(dir, { intermediates: true }).catch(() => {});
  const download = await FileSystem.downloadAsync(
    `${API_URL}/workouts/${journeyId}/${day}.zwo`,
    `${dir}download.zwo`,
    { headers: { Authorization: `Bearer ${await getToken()}` } },
  );
  if (download.status !== 200) throw new Error('The workout file could not be downloaded.');

  // The server names the file after the workout; keep that name for the Mac's Downloads folder.
  const header = download.headers['Content-Disposition'] || download.headers['content-disposition'] || '';
  const name = (header.match(/filename="([^"]+)"/)?.[1] || `${day} Workout.zwo`).replace(/ /g, '_');
  const target = `${dir}${name}`;
  await FileSystem.deleteAsync(target, { idempotent: true });
  await FileSystem.moveAsync({ from: download.uri, to: target });
  await Sharing.shareAsync(target, { mimeType: 'application/xml', UTI: 'public.xml', dialogTitle: name });
}
