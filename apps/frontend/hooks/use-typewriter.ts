import { useState, useEffect } from "react";

export const useTypewriter = (
  text: string | null,
  enabled: boolean = true,
  speed: number = 30,
) => {
  const [displayedText, setDisplayedText] = useState("");
  const [isTyping, setIsTyping] = useState(false);

  useEffect(() => {
    if (!text) {
      setDisplayedText("");
      setIsTyping(false);
      return;
    }

    if (!enabled) {
      setDisplayedText(text);
      setIsTyping(false);
      return;
    }

    setIsTyping(true);
    setDisplayedText("");

    // Split by words/whitespace to keep markdown tokens intact
    const words = text.split(/(\s+)/);
    let currentIndex = 0;
    let currentText = "";

    const intervalId = setInterval(() => {
      if (currentIndex >= words.length) {
        clearInterval(intervalId);
        setIsTyping(false);
        return;
      }

      currentText += words[currentIndex];
      setDisplayedText(currentText);
      currentIndex++;
    }, speed);

    return () => clearInterval(intervalId);
  }, [text, enabled, speed]);

  return { displayedText, isTyping };
};
