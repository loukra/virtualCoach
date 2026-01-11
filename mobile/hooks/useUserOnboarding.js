// mobile/hooks/useUserOnboarding.js
import { useState, useEffect } from 'react';
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
    
    return () => subscription.unsubscribe();
  }, []);

  const checkUserStatus = async (userId) => {
    setLoading(true);
    try {
        // 1. Check Strava
        const { data: stravaData } = await supabase
            .from('strava_connection')
            .select('user_id')
            .eq('user_id', userId)
            .maybeSingle();

        // 2. Check Profile
        const { data: profileData } = await supabase
            .from('profiles')
            .select('goal, sync_status')
            .eq('id', userId)
            .maybeSingle();

        const hasGoal = profileData?.goal && profileData.goal.trim().length > 0;
        const isSyncDone = profileData?.sync_status === 'completed';

        setStatus({
            stravaConnected: !!stravaData,
            profileSetupDone: !!hasGoal,
            syncCompleted: isSyncDone
        });

        // Trigger polling if needed
        if (!!stravaData && hasGoal && !isSyncDone) {
            pollSyncStatus(userId);
        }
    } catch (e) {
        console.error(e);
    } finally {
        setLoading(false);
    }
  };

  const pollSyncStatus = (userId) => {
    const interval = setInterval(async () => {
      const { data } = await supabase.from('profiles').select('sync_status').eq('id', userId).single();
      
      if (data?.sync_status === 'completed') {
        clearInterval(interval);
        setStatus(prev => ({ ...prev, syncCompleted: true }));
      } else if (data?.sync_status === 'failed') {
        clearInterval(interval);
        Alert.alert("Sync Error", "Something went wrong.");
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