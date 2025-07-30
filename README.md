# Muni Times - Home Assistant Integration

A Home Assistant custom integration that provides real-time transit arrival times using the 511.org API. This integration is based on the MMM-MuniTimes MagicMirror module.

## Features

- Real-time transit arrival information
- Support for multiple transit stops
- Line-specific icons (bus, trolley, cable car, metro)
- Configurable time formats (minutes, verbose, full time)
- Multiple arrival times per line
- Destination information
- Robust error handling with retry logic

## Installation

### HACS (Recommended)

1. Add this repository to HACS as a custom repository
2. Search for "Muni Times" in HACS
3. Install the integration
4. Restart Home Assistant

### Manual Installation

1. Copy the `ha_muni_times` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Go to Settings > Devices & Services
4. Click "Add Integration" and search for "Muni Times"

## Configuration

### API Key

You'll need a free API key from 511.org:

1. Visit [511.org Developer Resources](https://511.org/developers/)
2. Sign up for a free account
3. Generate an API key

### Integration Setup

1. Go to Settings > Devices & Services
2. Click "Add Integration"
3. Search for "Muni Times" and select it
4. Enter your configuration:
   - **API Key**: Your 511.org API key
   - **Agency**: Transit agency code (default: "SF" for San Francisco Muni)
   - **Update Interval**: How often to fetch data (default: 60 seconds)
   - **Max Results**: Maximum arrival times per stop (default: 3)
   - **Show Line Icons**: Display emoji icons for different line types
   - **Time Format**: Choose between "minutes", "verbose", or "full"
   - **Time Zone**: Your local timezone (default: America/Los_Angeles)

### Adding Stops

After setting up the integration, you'll need to add transit stops. This is currently done by modifying the integration's configuration data. In a future version, this will be done through the UI.

Edit your stops configuration by adding entries like this:

```yaml
stops:
  - stop_code: "13543"
    stop_name: "30th St & Church St"
    direction: "Northbound"
    line_names:
      "24": "24 Divisadero"
  - stop_code: "14000"
    stop_name: "30th St & Church St"
    direction: "To Downtown"
    line_names:
      "J": "J Church"
```

### Stop Configuration Options

- **stop_code**: The 511.org stop code (required)
- **stop_name**: Display name for the stop (optional)
- **direction**: Direction description (optional)
- **line_names**: Custom names for specific lines (optional)
- **destination_names**: Custom destination names (optional)

## Finding Stop Codes

To find stop codes for your area:

1. Visit [511.org](https://511.org)
2. Use their trip planner or real-time departures feature
3. Look at the URL or inspect the page source for stop codes
4. For SF Muni, you can also check the physical stop signs

## Usage

Once configured, the integration creates sensor entities for each stop:

- **Entity ID**: `sensor.muni_times_[stop_code]`
- **State**: Next arrival time for the first line
- **Attributes**: Detailed information about all arrivals

### Example Sensor Attributes

```yaml
stop_code: "13543"
stop_name: "30th St & Church St"
agency: "SF"
last_updated: "2023-12-07T10:30:00"
lines:
  - line: "🚌 24"
    line_ref: "24"
    destinations: ["Divisadero & North Point"]
    arrivals:
      - minutes: "3"
        formatted_time: "3 min"
        destination: "Divisadero & North Point"
        arrival_time: "2023-12-07T10:33:00"
      - minutes: "15"
        formatted_time: "15 min"
        destination: "Divisadero & North Point"
        arrival_time: "2023-12-07T10:45:00"
```

## Line Icons

The integration automatically adds emoji icons for different line types:

- 🚌 Regular bus
- 🚎 Trolleybus (electric bus)
- 🚟 Cable car
- 🚇 Metro/streetcar
- 🦉 Owl service (late night)
- 🚀 Express service

## Automation Examples

### Alert when next bus is arriving soon

```yaml
automation:
  - alias: "Bus Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.muni_times_13543
        below: 5
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: "Your bus arrives in {{ states('sensor.muni_times_13543') }}"
```

### Create a dashboard card

```yaml
type: entities
title: Transit Arrivals
entities:
  - entity: sensor.muni_times_13543
    name: "24 Divisadero - Northbound"
  - entity: sensor.muni_times_13538
    name: "24 Divisadero - Southbound"
```

## Troubleshooting

### No Data

- Verify your API key is correct
- Check that the stop codes are valid
- Ensure the agency code matches your transit system
- Check Home Assistant logs for error messages

### API Rate Limits

The 511.org API has rate limits. If you have many stops or very frequent updates, you may hit these limits. Consider:

- Increasing the update interval
- Reducing the number of stops
- Using fewer arrivals per stop

## Support

For issues and feature requests, please create an issue on the GitHub repository.

## License

This integration is released under the MIT License.
