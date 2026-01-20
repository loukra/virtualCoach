// mobile/context/JourneyContext.js
import React, { createContext, useState, useContext } from 'react';

const JourneyContext = createContext();

export const JourneyProvider = ({ children }) => {
  const [activeJourneyId, setActiveJourneyId] = useState(null);

  return (
    <JourneyContext.Provider value={{ activeJourneyId, setActiveJourneyId }}>
      {children}
    </JourneyContext.Provider>
  );
};

export const useJourney = () => useContext(JourneyContext);