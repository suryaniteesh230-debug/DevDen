import { BrowserRouter, Routes, Route } from "react-router-dom";

import Layout from "./components/Layout";
import Home from "./pages/Home";
import MonumentRecognition from "./pages/MonumentRecognition";
import TripPlanner from "./pages/TripPlanner";
import FoodExplorer from "./pages/FoodExplorer";
import LanguageLearning from "./pages/LanguageLearning";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Home />} />
          <Route path="/monument" element={<MonumentRecognition />} />
          <Route path="/trip-planner" element={<TripPlanner />} />
          <Route path="/food" element={<FoodExplorer />} />
          <Route path="/language" element={<LanguageLearning />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;