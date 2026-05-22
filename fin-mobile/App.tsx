import { StatusBar } from "expo-status-bar";
import { GoalsScreen } from "./src/features/goals/ui/GoalsScreen";

export default function App() {
  return (
    <>
      <GoalsScreen />
      <StatusBar style="dark" />
    </>
  );
}
