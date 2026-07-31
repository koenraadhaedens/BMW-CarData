# BMW-Cardata
# BMW CarData Home Assistant Integration (HACS)

Custom Home Assistant integration for BMW CarData authentication using OAuth2 Device Code Flow.

## What this does

- Adds a Home Assistant config flow for BMW CarData.
- Asks the user for a BMW CarData **Client ID**.
- Requests a **device code** from BMW OAuth.
- Displays the **user code** and verification URL.
- Exchanges the authorized device code for BMW tokens and stores them in the config entry.
- Automatically refreshes expired/expiring access tokens using the refresh token.
- Creates sensors, binary sensors, and device trackers from incoming MQTT telematics.
- Uses no BMW CarData business REST endpoints and sends no remote vehicle commands.

## Install with HACS

1. In HACS, open **Integrations**.
2. Add this repository as a **Custom repository**.
3. Select category **Integration**.
4. Install **BMW CarData**.
5. Restart Home Assistant.

## Setup in Home Assistant

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **BMW CarData**.
3. Enter your Client ID and MQTT stream topic from My BMW → CarData.
4. Follow the displayed authorization instructions (user code + URL).
5. Submit once authorized.

## Notes

- Entities remain unknown until their values arrive through MQTT.
- MQTT only publishes vehicle changes; there is no startup REST snapshot.
- You must subscribe your client to `cardata:streaming:read` before authorizing.

## MQTT streaming

The integration is inbound MQTT-only:

1. Open integration options in Home Assistant.
2. Set the stream topic from BMW CarData streaming credentials.
3. Stream host and port use BMW defaults automatically (`customer.streaming-cardata.bmwgroup.com:9000`).
4. The integration uses your BMW `gcid` as MQTT username and token as MQTT password.

If streaming was not enabled during initial setup, remove and re-add the integration with
streaming enabled. BMW must issue a new token containing the
`cardata:streaming:read` scope; changing the option alone cannot add that scope.

Existing entries authorized without `cardata:streaming:read` must be removed and re-added.
