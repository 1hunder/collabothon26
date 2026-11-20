import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { saveProgress } from '../questStore';

export default function WhatAreYouInto(): React.JSX.Element {
  const location = useLocation();
  useEffect(() => {
    saveProgress(location.pathname, null);
  }, [location.pathname]);
  return <h1 className="text-xl font-bold">What are you into?</h1>;
}
