// mobile/context/SessionContext.js
import React, { createContext, useContext } from 'react';

const SessionContext = createContext(null);

export const SessionProvider = ({ value, children }) => (
  <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
);

export const useSessionContext = () => useContext(SessionContext);
