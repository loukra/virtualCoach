// mobile/hooks/useUserOnboarding.js
import { useState, useEffect, useRef } from 'react';
import { supabase } from '../lib/supabase';
import { Alert } from 'react-native';

export function useUserOnboarding() {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  
  // State object to keep things organized
  const [status, setStatus] = useState({
    stravaConnected: false,
    profileSetupDone: false,
    syncCompleted: false,
  });

  const pollingRef = useRef(null);
  const stopPolling = () => {
    if (pollingRef.current) clearInterval(pollingRef.current);
    pollingRef.current = null;
  };

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      if (session) checkUserStatus(session.user.id);
      else setLoading(false);
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      if (session) checkUserStatus(session.user.id);
      else setLoading(false);
    });
    
    return () => {
      subscription.unsubscribe();
      stopPolling();
    };
  }, []);

  const checkUserStatus = async (userId) => {
    setLoading(true);
    try {
        // Strava tokens are not readable from the app; the backend sets strava_connected.
        const { data: profileData } = await supabase
            .from('profiles')
            .select('goal, sync_status, strava_connected')
            .eq('id', userId)
            .maybeSingle();

        const hasGoal = profileData?.goal && profileData.goal.trim().length > 0;
        const isSyncDone = profileData?.sync_status === 'completed';
        const stravaConnected = !!profileData?.strava_connected;

        setStatus({
            stravaConnected,
            profileSetupDone: !!hasGoal,
            syncCompleted: isSyncDone
        });

        // Trigger polling if needed
        if (stravaConnected && hasGoal && !isSyncDone) {
            pollSyncStatus(userId);
        }
    } catch (e) {
        console.error(e);
    } finally {
        setLoading(false);
    }
  };

  const pollSyncStatus = (userId) => {
    stopPolling();
    pollingRef.current = setInterval(async () => {
      const { data } = await supabase.from('profiles').select('sync_status').eq('id', userId).single();

      if (data?.sync_status === 'completed') {
        stopPolling();
        setStatus(prev => ({ ...prev, syncCompleted: true }));
      } else if (data?.sync_status === 'failed') {
        stopPolling();
        Alert.alert("Sync Error", "Importing your Strava history failed. Please try again.");
      }
    }, 3000);
  };

  // We return the state and the function to refresh it manually
  return { 
    session, 
    loading, 
    ...status, 
    refreshStatus: () => checkUserStatus(session.user.id) 
  };
}