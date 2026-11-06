//! Power capability (SYS-PWR-01): battery state from UPower, power-off,
//! reboot and suspend through systemd-logind.
//!
//! Read: `power.get_status`. Change: `power.request_action`, which always
//! requires an explicit `confirmed: true` and is only reported as accepted
//! when logind accepted the call. Authorisation is logind/polkit's: an active
//! local session may power off; otherwise polkit asks or refuses.

use super::{EiraError, ErrorCode};
use serde::{Deserialize, Serialize};
use std::future::Future;
use std::pin::Pin;

pub type BoxFuture<'a, T> = Pin<Box<dyn Future<Output = T> + Send + 'a>>;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum PowerAction {
    Poweroff,
    Reboot,
    Suspend,
}

impl PowerAction {
    fn label(self) -> &'static str {
        match self {
            Self::Poweroff => "slukke",
            Self::Reboot => "genstarte",
            Self::Suspend => "slumre",
        }
    }
}

/// logind's answer to CanPowerOff/CanReboot/CanSuspend, in GUI terms.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Availability {
    /// "yes": allowed without further authentication.
    Available,
    /// "challenge": allowed after polkit authentication.
    NeedsAuthentication,
    /// "no", "na", inhibited, or logind not reachable.
    Unavailable,
}

impl Availability {
    pub fn from_logind(answer: &str) -> Self {
        match answer {
            "yes" => Self::Available,
            "challenge" => Self::NeedsAuthentication,
            _ => Self::Unavailable,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum BatteryState {
    Charging,
    Discharging,
    Empty,
    FullyCharged,
    PendingCharge,
    PendingDischarge,
    Unknown,
}

impl BatteryState {
    /// UPower Device.State (u32).
    pub fn from_upower(state: u32) -> Self {
        match state {
            1 => Self::Charging,
            2 => Self::Discharging,
            3 => Self::Empty,
            4 => Self::FullyCharged,
            5 => Self::PendingCharge,
            6 => Self::PendingDischarge,
            _ => Self::Unknown,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Battery {
    pub percentage: f64,
    pub state: BatteryState,
    /// Seconds; absent when UPower does not know.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub time_to_empty_s: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub time_to_full_s: Option<i64>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct PowerActions {
    pub poweroff: Availability,
    pub reboot: Availability,
    pub suspend: Availability,
}

impl PowerActions {
    fn get(&self, action: PowerAction) -> Availability {
        match action {
            PowerAction::Poweroff => self.poweroff,
            PowerAction::Reboot => self.reboot,
            PowerAction::Suspend => self.suspend,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct PowerStatus {
    /// None when UPower is not running (unknown is not the same as "no").
    pub on_battery: Option<bool>,
    /// None on machines without a battery, or when UPower is not running.
    pub battery: Option<Battery>,
    pub actions: PowerActions,
    /// Which services answered, so the GUI can show unknown states honestly.
    pub sources: PowerSources,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct PowerSources {
    pub upower: bool,
    pub logind: bool,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PowerActionInput {
    pub action: PowerAction,
    #[serde(default)]
    pub confirmed: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct PowerActionResult {
    pub action: PowerAction,
    /// logind accepted the request. The machine changing state is what
    /// confirms success; the GUI must not claim more than "accepted".
    pub accepted: bool,
}

pub trait PowerAdapter: Send + Sync {
    fn status(&self) -> BoxFuture<'_, Result<PowerStatus, EiraError>>;
    fn perform(&self, action: PowerAction) -> BoxFuture<'_, Result<(), EiraError>>;
}

pub async fn request_action(
    adapter: &dyn PowerAdapter,
    input: PowerActionInput,
) -> Result<PowerActionResult, EiraError> {
    if !input.confirmed {
        return Err(EiraError::new(
            ErrorCode::ConfirmationRequired,
            format!("Bekræft, at computeren skal {}", input.action.label()),
        ));
    }
    let status = adapter.status().await?;
    if status.actions.get(input.action) == Availability::Unavailable {
        let message = if status.sources.logind {
            format!("Computeren kan ikke {} lige nu", input.action.label())
        } else {
            "Strømstyring (systemd-logind) er ikke tilgængelig".to_owned()
        };
        return Err(EiraError::new(ErrorCode::CapabilityUnavailable, message));
    }
    adapter.perform(input.action).await?;
    Ok(PowerActionResult {
        action: input.action,
        accepted: true,
    })
}

/// The real adapter: UPower and systemd-logind on the system D-Bus.
pub struct DbusPowerAdapter {
    connection: zbus::Connection,
}

const LOGIN1: &str = "org.freedesktop.login1";
const LOGIN1_PATH: &str = "/org/freedesktop/login1";
const LOGIN1_MANAGER: &str = "org.freedesktop.login1.Manager";
const UPOWER: &str = "org.freedesktop.UPower";
const UPOWER_PATH: &str = "/org/freedesktop/UPower";
const DISPLAY_DEVICE_PATH: &str = "/org/freedesktop/UPower/devices/DisplayDevice";
const UPOWER_DEVICE: &str = "org.freedesktop.UPower.Device";
/// UPower Device.Type for a battery.
const UPOWER_TYPE_BATTERY: u32 = 2;

impl DbusPowerAdapter {
    pub async fn system() -> Result<Self, EiraError> {
        let connection = zbus::Connection::system().await.map_err(|_| {
            EiraError::new(
                ErrorCode::CapabilityUnavailable,
                "Systemets D-Bus er ikke tilgængelig",
            )
        })?;
        Ok(Self { connection })
    }

    #[cfg_attr(not(test), allow(dead_code))]
    pub fn with_connection(connection: zbus::Connection) -> Self {
        Self { connection }
    }

    async fn proxy(
        &self,
        service: &'static str,
        path: &'static str,
        interface: &'static str,
    ) -> zbus::Result<zbus::Proxy<'_>> {
        zbus::Proxy::new(&self.connection, service, path, interface).await
    }

    async fn can(&self, method: &str) -> Option<String> {
        let proxy = self.proxy(LOGIN1, LOGIN1_PATH, LOGIN1_MANAGER).await.ok()?;
        proxy.call::<_, _, String>(method, &()).await.ok()
    }

    async fn upower(&self) -> Option<(bool, Option<Battery>)> {
        let root = self.proxy(UPOWER, UPOWER_PATH, UPOWER).await.ok()?;
        let on_battery: bool = root.get_property("OnBattery").await.ok()?;
        let battery = async {
            let device = self
                .proxy(UPOWER, DISPLAY_DEVICE_PATH, UPOWER_DEVICE)
                .await
                .ok()?;
            let present: bool = device.get_property("IsPresent").await.ok()?;
            let kind: u32 = device.get_property("Type").await.ok()?;
            if !present || kind != UPOWER_TYPE_BATTERY {
                return None;
            }
            let positive = |value: i64| (value > 0).then_some(value);
            Some(Battery {
                percentage: device.get_property("Percentage").await.ok()?,
                state: BatteryState::from_upower(device.get_property("State").await.ok()?),
                time_to_empty_s: device
                    .get_property::<i64>("TimeToEmpty")
                    .await
                    .ok()
                    .and_then(positive),
                time_to_full_s: device
                    .get_property::<i64>("TimeToFull")
                    .await
                    .ok()
                    .and_then(positive),
            })
        }
        .await;
        Some((on_battery, battery))
    }
}

impl PowerAdapter for DbusPowerAdapter {
    fn status(&self) -> BoxFuture<'_, Result<PowerStatus, EiraError>> {
        Box::pin(async move {
            let upower = self.upower().await;
            let upower_answered = upower.is_some();
            let poweroff = self.can("CanPowerOff").await;
            let reboot = self.can("CanReboot").await;
            let suspend = self.can("CanSuspend").await;
            let logind = poweroff.is_some() || reboot.is_some() || suspend.is_some();
            let availability = |answer: Option<String>| {
                answer
                    .as_deref()
                    .map_or(Availability::Unavailable, Availability::from_logind)
            };
            Ok(PowerStatus {
                on_battery: upower.as_ref().map(|(on_battery, _)| *on_battery),
                battery: upower.and_then(|(_, battery)| battery),
                actions: PowerActions {
                    poweroff: availability(poweroff),
                    reboot: availability(reboot),
                    suspend: availability(suspend),
                },
                sources: PowerSources {
                    upower: upower_answered,
                    logind,
                },
            })
        })
    }

    fn perform(&self, action: PowerAction) -> BoxFuture<'_, Result<(), EiraError>> {
        Box::pin(async move {
            let method = match action {
                PowerAction::Poweroff => "PowerOff",
                PowerAction::Reboot => "Reboot",
                PowerAction::Suspend => "Suspend",
            };
            let proxy = self
                .proxy(LOGIN1, LOGIN1_PATH, LOGIN1_MANAGER)
                .await
                .map_err(|_| {
                    EiraError::new(
                        ErrorCode::CapabilityUnavailable,
                        "systemd-logind er ikke tilgængelig",
                    )
                })?;
            // interactive=true lets polkit ask for authentication when required.
            proxy
                .call::<_, _, ()>(method, &(true,))
                .await
                .map_err(|error| map_logind_error(&error, action))
        })
    }
}

fn map_logind_error(error: &zbus::Error, action: PowerAction) -> EiraError {
    let name = match error {
        zbus::Error::MethodError(name, _, _) => name.as_str().to_owned(),
        _ => String::new(),
    };
    if name.ends_with("AccessDenied") || name.ends_with("InteractiveAuthorizationRequired") {
        EiraError::new(
            ErrorCode::PermissionDenied,
            format!(
                "Du har ikke tilladelse til at {} computeren",
                action.label()
            ),
        )
    } else if name.ends_with("BlockedByInhibitor") || name.contains("Inhibit") {
        EiraError::new(
            ErrorCode::CapabilityUnavailable,
            format!(
                "Et program forhindrer lige nu, at computeren kan {}",
                action.label()
            ),
        )
    } else {
        EiraError::new(
            ErrorCode::IoError,
            format!("Computeren kunne ikke {}", action.label()),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    pub struct MockPower {
        pub status: PowerStatus,
        pub performed: Mutex<Vec<PowerAction>>,
        pub fail_with: Option<ErrorCode>,
    }

    impl PowerAdapter for MockPower {
        fn status(&self) -> BoxFuture<'_, Result<PowerStatus, EiraError>> {
            let status = self.status.clone();
            Box::pin(async move { Ok(status) })
        }
        fn perform(&self, action: PowerAction) -> BoxFuture<'_, Result<(), EiraError>> {
            Box::pin(async move {
                if let Some(code) = self.fail_with {
                    return Err(EiraError::new(code, "nej"));
                }
                self.performed.lock().unwrap().push(action);
                Ok(())
            })
        }
    }

    pub fn status(poweroff: Availability) -> PowerStatus {
        PowerStatus {
            on_battery: Some(false),
            battery: None,
            actions: PowerActions {
                poweroff,
                reboot: Availability::Available,
                suspend: Availability::Unavailable,
            },
            sources: PowerSources {
                upower: true,
                logind: true,
            },
        }
    }

    pub fn mock(poweroff: Availability) -> MockPower {
        MockPower {
            status: status(poweroff),
            performed: Mutex::new(Vec::new()),
            fail_with: None,
        }
    }

    fn input(action: PowerAction, confirmed: bool) -> PowerActionInput {
        PowerActionInput { action, confirmed }
    }

    #[tokio::test]
    async fn unconfirmed_actions_are_never_performed() {
        let power = mock(Availability::Available);
        let error = request_action(&power, input(PowerAction::Poweroff, false))
            .await
            .unwrap_err();
        assert_eq!(error.code, ErrorCode::ConfirmationRequired);
        assert!(power.performed.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn confirmed_available_action_is_accepted() {
        let power = mock(Availability::NeedsAuthentication);
        let result = request_action(&power, input(PowerAction::Poweroff, true))
            .await
            .unwrap();
        assert_eq!(
            result,
            PowerActionResult {
                action: PowerAction::Poweroff,
                accepted: true
            }
        );
        assert_eq!(
            *power.performed.lock().unwrap(),
            vec![PowerAction::Poweroff]
        );
    }

    #[tokio::test]
    async fn unavailable_action_fails_closed() {
        let power = mock(Availability::Available);
        let error = request_action(&power, input(PowerAction::Suspend, true))
            .await
            .unwrap_err();
        assert_eq!(error.code, ErrorCode::CapabilityUnavailable);
        assert!(power.performed.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn service_refusal_is_reported_not_hidden() {
        let mut power = mock(Availability::Available);
        power.fail_with = Some(ErrorCode::PermissionDenied);
        let error = request_action(&power, input(PowerAction::Reboot, true))
            .await
            .unwrap_err();
        assert_eq!(error.code, ErrorCode::PermissionDenied);
    }

    #[test]
    fn maps_service_values() {
        assert_eq!(Availability::from_logind("yes"), Availability::Available);
        assert_eq!(
            Availability::from_logind("challenge"),
            Availability::NeedsAuthentication
        );
        assert_eq!(Availability::from_logind("no"), Availability::Unavailable);
        assert_eq!(Availability::from_logind("na"), Availability::Unavailable);
        assert_eq!(BatteryState::from_upower(2), BatteryState::Discharging);
        assert_eq!(BatteryState::from_upower(99), BatteryState::Unknown);
    }
}

#[cfg(test)]
pub(crate) use tests::mock as mock_power;

/// Integration tests against real D-Bus: a private dbus-daemon with fake
/// logind and UPower services, so method names, signatures, properties and
/// error mapping are exercised exactly as on Ubuntu.
#[cfg(test)]
mod dbus_tests {
    use super::*;
    use std::process::{Child, Command, Stdio};
    use std::sync::{Arc, Mutex};

    struct Bus {
        daemon: Child,
        address: String,
    }

    impl Drop for Bus {
        fn drop(&mut self) {
            let _ = self.daemon.kill();
            let _ = self.daemon.wait();
        }
    }

    fn private_bus() -> Option<Bus> {
        let dir = std::env::temp_dir().join(format!(
            "eira-dbus-{}-{}",
            std::process::id(),
            rand_suffix()
        ));
        std::fs::create_dir_all(&dir).ok()?;
        let address = format!("unix:path={}", dir.join("bus").display());
        let config = dir.join("bus.conf");
        std::fs::write(
            &config,
            format!(
                r#"<busconfig><type>session</type><listen>{address}</listen>
                <policy context="default"><allow send_destination="*" eavesdrop="true"/>
                <allow eavesdrop="true"/><allow own="*"/><allow user="*"/></policy></busconfig>"#
            ),
        )
        .ok()?;
        let daemon = Command::new("dbus-daemon")
            .arg(format!("--config-file={}", config.display()))
            .arg("--nofork")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .ok()?;
        for _ in 0..100 {
            if dir.join("bus").exists() {
                return Some(Bus { daemon, address });
            }
            std::thread::sleep(std::time::Duration::from_millis(20));
        }
        None
    }

    fn rand_suffix() -> u64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos() as u64)
            .unwrap_or(0)
    }

    struct FakeLogin1 {
        calls: Arc<Mutex<Vec<(String, bool)>>>,
    }

    #[zbus::interface(name = "org.freedesktop.login1.Manager")]
    impl FakeLogin1 {
        fn can_power_off(&self) -> String {
            "yes".into()
        }
        fn can_reboot(&self) -> String {
            "challenge".into()
        }
        fn can_suspend(&self) -> String {
            "na".into()
        }
        fn power_off(&self, interactive: bool) {
            self.calls
                .lock()
                .unwrap()
                .push(("PowerOff".into(), interactive));
        }
        fn reboot(&self, _interactive: bool) -> zbus::fdo::Result<()> {
            Err(zbus::fdo::Error::AccessDenied("polkit said no".into()))
        }
    }

    struct FakeUPower;

    #[zbus::interface(name = "org.freedesktop.UPower")]
    impl FakeUPower {
        #[zbus(property)]
        fn on_battery(&self) -> bool {
            true
        }
    }

    struct FakeBattery;

    #[zbus::interface(name = "org.freedesktop.UPower.Device")]
    impl FakeBattery {
        #[zbus(property)]
        fn is_present(&self) -> bool {
            true
        }
        #[zbus(property, name = "Type")]
        fn kind(&self) -> u32 {
            2
        }
        #[zbus(property)]
        fn percentage(&self) -> f64 {
            73.0
        }
        #[zbus(property)]
        fn state(&self) -> u32 {
            2
        }
        #[zbus(property)]
        fn time_to_empty(&self) -> i64 {
            5400
        }
        #[zbus(property)]
        fn time_to_full(&self) -> i64 {
            0
        }
    }

    async fn connect(address: &str) -> zbus::connection::Builder<'static> {
        zbus::connection::Builder::address(address).expect("bus address")
    }

    #[tokio::test]
    async fn reads_status_and_calls_logind_over_real_dbus() {
        let Some(bus) = private_bus() else {
            eprintln!("dbus-daemon not available; skipping");
            return;
        };
        let calls = Arc::new(Mutex::new(Vec::new()));
        let _logind = connect(&bus.address)
            .await
            .name("org.freedesktop.login1")
            .unwrap()
            .serve_at(
                "/org/freedesktop/login1",
                FakeLogin1 {
                    calls: Arc::clone(&calls),
                },
            )
            .unwrap()
            .build()
            .await
            .expect("fake logind");
        let _upower = connect(&bus.address)
            .await
            .name("org.freedesktop.UPower")
            .unwrap()
            .serve_at("/org/freedesktop/UPower", FakeUPower)
            .unwrap()
            .serve_at("/org/freedesktop/UPower/devices/DisplayDevice", FakeBattery)
            .unwrap()
            .build()
            .await
            .expect("fake upower");
        let client = connect(&bus.address).await.build().await.expect("client");
        let adapter = DbusPowerAdapter::with_connection(client);

        let status = adapter.status().await.unwrap();
        assert_eq!(status.on_battery, Some(true));
        assert_eq!(
            status.battery,
            Some(Battery {
                percentage: 73.0,
                state: BatteryState::Discharging,
                time_to_empty_s: Some(5400),
                time_to_full_s: None,
            })
        );
        assert_eq!(status.actions.poweroff, Availability::Available);
        assert_eq!(status.actions.reboot, Availability::NeedsAuthentication);
        assert_eq!(status.actions.suspend, Availability::Unavailable);
        assert_eq!(
            status.sources,
            PowerSources {
                upower: true,
                logind: true
            }
        );

        let accepted = request_action(
            &adapter,
            PowerActionInput {
                action: PowerAction::Poweroff,
                confirmed: true,
            },
        )
        .await
        .unwrap();
        assert!(accepted.accepted);
        assert_eq!(*calls.lock().unwrap(), vec![("PowerOff".to_owned(), true)]);

        let denied = request_action(
            &adapter,
            PowerActionInput {
                action: PowerAction::Reboot,
                confirmed: true,
            },
        )
        .await
        .unwrap_err();
        assert_eq!(denied.code, ErrorCode::PermissionDenied);
    }

    #[tokio::test]
    async fn missing_services_are_unknown_not_errors() {
        let Some(bus) = private_bus() else {
            eprintln!("dbus-daemon not available; skipping");
            return;
        };
        let client = connect(&bus.address).await.build().await.expect("client");
        let adapter = DbusPowerAdapter::with_connection(client);
        let status = adapter.status().await.unwrap();
        assert_eq!(status.on_battery, None);
        assert_eq!(status.battery, None);
        assert_eq!(status.actions.poweroff, Availability::Unavailable);
        assert_eq!(
            status.sources,
            PowerSources {
                upower: false,
                logind: false
            }
        );
        let error = request_action(
            &adapter,
            PowerActionInput {
                action: PowerAction::Poweroff,
                confirmed: true,
            },
        )
        .await
        .unwrap_err();
        assert_eq!(error.code, ErrorCode::CapabilityUnavailable);
        assert!(error.message.contains("systemd-logind"));
    }
}
