import { useEffect, useState, useCallback } from "react";

export interface WorkflowEvent {
  event_type: string;
  workflow_id: string;
  timestamp: string;
  data: {
    stage_name: string;
    document_id?: string;
    workflow_id?: string;
    status: string;
    message: string;
    has_output?: boolean;
    metadata?: any;
  };
}

export function useWorkflowStream(workflowId: string | null) {
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const connect = useCallback(() => {
    if (!workflowId) return;

    const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    if (!token) {
      setError("Authentication token missing");
      return;
    }

    const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const url = `${baseUrl}/api/v1/workflows/stream/${workflowId}?token=${token}`;

    const eventSource = new EventSource(url);

    eventSource.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    eventSource.onerror = (err) => {
      console.error("SSE Error:", err);
      setError("Connection to event stream failed");
      eventSource.close();
      setIsConnected(false);
    };

    // Generic message handler for all event types we defined
    const eventTypes = [
      "workflow:started",
      "workflow:progress",
      "workflow:completed",
      "workflow:failed",
      "stage:started",
      "stage:completed",
      "stage:failed"
    ];

    eventTypes.forEach((type) => {
      eventSource.addEventListener(type, (event: MessageEvent) => {
        const payload: WorkflowEvent = JSON.parse(event.data);
        setEvents((prev) => [...prev, payload]);

        if (type === "workflow:completed" || type === "workflow:failed") {
          setIsComplete(true);
          eventSource.close();
          setIsConnected(false);
        }
      });
    });

    return () => {
      eventSource.close();
      setIsConnected(false);
    };
  }, [workflowId]);

  useEffect(() => {
    let cleanup: (() => void) | undefined;
    if (workflowId) {
      cleanup = connect();
    }
    return () => cleanup?.();
  }, [workflowId, connect]);

  return { events, isConnected, isComplete, error, connect };
}
