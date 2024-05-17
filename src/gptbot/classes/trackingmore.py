import trackingmore

from .logging import Logger

from typing import Tuple, Optional

class TrackingMore:
    api_key: str
    logger: Logger
    client: trackingmore.TrackingMore

    api_code: str = "trackingmore"
    parcel_api: str = "trackingmore"

    operator: str = "TrackingMore ([https://www.trackingmore.com](https://www.trackingmore.com))"

    def __init__(self, api_key: str, logger: Optional[Logger] = None):
        self.api_key: str = api_key
        self.logger: Logger = logger or Logger()
        self.client = trackingmore.TrackingMore(self.api_key)

    def lookup_parcel(self, query: str, carrier: Optional[str] = None, user: Optional[str] = None) -> Tuple[str, int]:
        self.logger.log(f"Querying TrackingMore for {query}")

        if query == "carriers":
            response = "\n".join(f"* {carrier['courier_name']} - {carrier['courier_code']}" for carrier in self.client.get_carriers())
            return response, 1

        response = self.client.track_shipment(query)

        return response, 1