import { useCallback, useReducer } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { Message } from "../../types";

type MessageAction = { type: "replace"; value: SetStateAction<Message[]> };

function messageReducer(state: Message[], action: MessageAction): Message[] {
  return typeof action.value === "function" ? action.value(state) : action.value;
}

/** Keeps the streaming message state isolated from the application shell. */
export function useMessageState(initial: Message[]): [Message[], Dispatch<SetStateAction<Message[]>>] {
  const [messages, dispatch] = useReducer(messageReducer, initial);
  const setMessages = useCallback<Dispatch<SetStateAction<Message[]>>>(
    value => dispatch({ type: "replace", value }),
    [],
  );
  return [messages, setMessages];
}
