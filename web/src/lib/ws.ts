/**
 * Auto-reconnecting WebSocket wrapper.
 * Emits parsed JSON messages via callback.
 */

export type WsMessage = {
  type: string;
  data: any;
};

export type WsOptions = {
  onMessage: (msg: WsMessage) => void;
  onOpen?: () => void;
  onClose?: () => void;
};

export class RadioSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private opts: WsOptions;
  private reconnectDelay = 1000;
  private maxDelay = 10000;
  private closed = false;

  constructor(opts: WsOptions) {
    this.opts = opts;
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    this.url = `${proto}//${location.host}/ws`;
    this.connect();
  }

  private connect() {
    if (this.closed) return;

    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      this.reconnectDelay = 1000;
      this.opts.onOpen?.();
    };

    this.ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data) as WsMessage;
        this.opts.onMessage(msg);
      } catch {
        // ignore malformed messages
      }
    };

    this.ws.onclose = () => {
      this.opts.onClose?.();
      if (!this.closed) {
        setTimeout(() => this.connect(), this.reconnectDelay);
        this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxDelay);
      }
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  send(type: string, data: Record<string, any> = {}) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, ...data }));
    }
  }

  close() {
    this.closed = true;
    this.ws?.close();
  }
}
