# Northeast Car Parks — Home Assistant

[![GitHub](https://img.shields.io/github/stars/06benste/northeastcarparks?style=social)](https://github.com/06benste/northeastcarparks)

Custom Home Assistant integration for live car park occupancy in the North East of England, using the [UTMC Open Data API](https://www.netraveldata.co.uk/?page_id=32) (v2) via [netraveldata.co.uk](https://www.netraveldata.co.uk/).

Each configured car park appears as one device with sensors for capacity, occupancy, spaces free, state, and address.

## Requirements

- Home Assistant **2024.11** or newer
- A free **netraveldata.co.uk** account (see below)
- Internet access to `www.netraveldata.co.uk`

## Installation

### Manual install

1. Copy the `custom_components/northeast_carparks` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and search for **Northeast Car Parks**.

### HACS (custom repository)

1. In HACS, open **Integrations → ⋮ → Custom repositories**.
2. Add repository **`https://github.com/06benste/northeastcarparks`** and category **Integration**.
3. Install **Northeast Car Parks** from HACS.
4. Restart Home Assistant and add the integration as above.

## UTMC login credentials

The API uses **HTTP Basic Auth**. You need a username and password from netraveldata — not your Home Assistant login.

1. Register for a free account at **[netraveldata.co.uk](https://www.netraveldata.co.uk/)** (registration link is on their site; see also the [Car Parks data page](https://www.netraveldata.co.uk/?page_id=32)).
2. After registration, use the **username** and **password** from that account when the integration prompts you during setup.
3. Credentials are stored in the Home Assistant config entry (one set is shared if you add multiple car parks).

If setup fails with a connection error, check that your account is active and that you can log in on the netraveldata website. The integration sends a `User-Agent` header because the API returns HTTP 403 without one.

## Adding car parks

- **First car park:** Settings → Add integration → Northeast Car Parks → enter UTMC credentials → pick a car park from the list.
- **More car parks:** Open the integration → **Add device** → choose another car park (already configured sites are hidden).
- **Update credentials:** Integration or device → **Configure** → update username/password (applies to all Northeast Car Parks devices).

Data is refreshed about **every 60 seconds**.

## Car parks with live occupancy data

Only car parks that publish reliable live occupancy on the UTMC dynamic feed are offered in the setup list. These **16** sites are supported (IDs match the API `systemCodeNumber`):

| ID | Name |
| --- | --- |
| `CP0050` | Eldon Square |
| `CP0049` | Eldon Garden |
| `CP0021` | Dean Street |
| `CP_NC_MANORS` | Manors |
| `CP_NC_ELLSPL` | Ellison Place |
| `PR001` | Four Lane Ends Interchange |
| `PR002` | Callerton Parkway Metro |
| `PR003` | Bank Foot Metro |
| `PR004` | East Boldon Metro |
| `PR005` | Fellgate Metro |
| `PR007` | Kingston Park Metro |
| `PR009` | Regent Centre Interchange |
| `PR010` | Stadium of Light Metro |
| `PR012` | Northumberland Park Metro |
| `VMSLCP002` | Heworth Interchange (Long Stay) |
| `VMSLCP003` | Heworth Interchange (Short Stay) |

Other car parks may appear in the raw UTMC feeds but are **not** listed in Home Assistant because they do not provide consistent live occupancy for this integration.

## Entities per device

| Sensor | Description |
| --- | --- |
| Name | Short name from UTMC |
| Address | Long description / address |
| Capacity | Total spaces (integer) |
| Occupancy | Spaces occupied (integer) |
| Spaces free | Capacity minus occupancy (integer) |
| State | e.g. SPACES, ALMOST FULL, FULL, OPEN, CLOSED |

## Data source & attribution

- Data: [NECA / UTMC Open Data](https://www.netraveldata.co.uk/?page_id=32)  
- API specification: [Open Data Service API (PDF)](https://www.netraveldata.co.uk/wp-content/uploads/2015/11/333551-OpenDataService-APISpecification.pdf)

This integration is not affiliated with NECA, netraveldata, or Tyne & Wear UTMC.

## License

MIT — see [LICENSE](LICENSE).
