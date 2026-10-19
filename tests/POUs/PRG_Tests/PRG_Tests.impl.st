// Все зарегистрированные наборы выполняются параллельно; итоги — в журнал
// устройства (логгер coUnit) и в XML-файл xUnit
coUnit.RUN();

// AreAllTestsFinished() вызывается после RUN(): у метода есть побочный эффект на первом цикле
xAllFinished := fbProjectCfgTest.AreAllTestsFinished();
