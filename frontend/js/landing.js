/**
 * METLINK — Public Landing Page Module
 * Pure Vanilla ES6+ JavaScript.
 * Coordinates navbar, hero carousel, SVG metric rings, sticky stacking cards,
 * bilingual USSD guide, live market prices chart, and copyright year.
 */

/**
 * Shared utility: Trigger a callback once when an element intersects the viewport.
 * Falls back immediately if IntersectionObserver is unsupported or reduced motion is preferred.
 */
function observeOnce(element, callback, threshold = 0.2) {
  if (!element) return;
  if (!('IntersectionObserver' in window)) {
    callback(element);
    return;
  }
  const observer = new IntersectionObserver((entries, obs) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        callback(entry.target);
        obs.unobserve(entry.target);
      }
    });
  }, { threshold });
  observer.observe(element);
}

/**
 * Check if the user has requested reduced motion.
 */
function prefersReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * Feature A: Navbar Sticky Shadow, Hamburger Menu & Scrollspy
 */
function initNav() {
  const navbar = document.getElementById('lpNavbar');
  const hamburger = document.getElementById('lpHamburger');
  const navMenu = document.getElementById('lpNavMenu');
  const navLinks = document.querySelectorAll('.lp-nav-link');

  if (!navbar) return;

  // 1. Scroll shadow state
  const handleScroll = () => {
    if (window.scrollY > 20) {
      navbar.classList.add('lp-scrolled');
    } else {
      navbar.classList.remove('lp-scrolled');
    }
  };
  window.addEventListener('scroll', handleScroll, { passive: true });
  handleScroll();

  // 2. Mobile hamburger menu
  if (hamburger && navMenu) {
    const toggleMenu = (open) => {
      const willOpen = open !== undefined ? open : !navMenu.classList.contains('lp-menu-open');
      navMenu.classList.toggle('lp-menu-open', willOpen);
      hamburger.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
    };

    hamburger.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleMenu();
    });

    // Close on link click
    navMenu.querySelectorAll('a').forEach(link => {
      link.addEventListener('click', () => toggleMenu(false));
    });

    // Close on Escape key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && navMenu.classList.contains('lp-menu-open')) {
        toggleMenu(false);
        hamburger.focus();
      }
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
      if (navMenu.classList.contains('lp-menu-open') && !navbar.contains(e.target)) {
        toggleMenu(false);
      }
    });
  }

  // 3. Scrollspy with IntersectionObserver
  const sections = document.querySelectorAll('section[id], header[id]');
  if ('IntersectionObserver' in window && sections.length > 0) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const id = entry.target.getAttribute('id');
          navLinks.forEach(link => {
            const href = link.getAttribute('href') || '';
            if (href === `#${id}`) {
              link.classList.add('lp-active');
            } else {
              link.classList.remove('lp-active');
            }
          });
        }
      });
    }, {
      rootMargin: '-20% 0px -70% 0px',
      threshold: 0
    });

    sections.forEach(sec => observer.observe(sec));
  }
}

/**
 * Feature B: Hero Carousel Cross-Fade & Controls
 */
function initCarousel() {
  const carousel = document.getElementById('lpHeroCarousel');
  if (!carousel) return;

  const slides = carousel.querySelectorAll('.lp-carousel-slide');
  const dots = document.querySelectorAll('.lp-carousel-dot');
  if (slides.length <= 1) return;

  let currentIdx = 0;
  let intervalId = null;
  let isPaused = false;
  const slideDuration = 4500;

  function showSlide(idx) {
    currentIdx = (idx + slides.length) % slides.length;
    slides.forEach((slide, i) => {
      if (i === currentIdx) {
        slide.classList.add('lp-slide-active');
      } else {
        slide.classList.remove('lp-slide-active');
      }
    });

    dots.forEach((dot, i) => {
      if (i === currentIdx) {
        dot.setAttribute('aria-current', 'true');
      } else {
        dot.removeAttribute('aria-current');
      }
    });
  }

  function startAutoplay() {
    if (prefersReducedMotion()) return;
    if (intervalId) clearInterval(intervalId);
    intervalId = setInterval(() => {
      if (!isPaused) {
        showSlide(currentIdx + 1);
      }
    }, slideDuration);
  }

  function stopAutoplay() {
    if (intervalId) {
      clearInterval(intervalId);
      intervalId = null;
    }
  }

  // Dot button click handlers
  dots.forEach((dot, i) => {
    dot.addEventListener('click', () => {
      showSlide(i);
      startAutoplay(); // Reset timer after manual jump
    });
  });

  // Pause on hover
  carousel.addEventListener('mouseenter', () => { isPaused = true; });
  carousel.addEventListener('mouseleave', () => { isPaused = false; });

  // Pause on focus within carousel
  carousel.addEventListener('focusin', () => { isPaused = true; });
  carousel.addEventListener('focusout', () => { isPaused = false; });

  // Pause when tab is hidden
  document.addEventListener('visibilitychange', () => {
    isPaused = document.hidden;
  });

  // Initialize first slide and start autoplay if motion is allowed
  showSlide(0);
  startAutoplay();
}

/**
 * Feature C: Animated Metric Rings and Live Market Count
 */
function initRings() {
  const problemSection = document.getElementById('problem');
  if (!problemSection) return;

  const marketCountVal = document.getElementById('lpMarketCountVal');

  // 1. Fetch live market count from API
  if (marketCountVal) {
    if (typeof MetlinkAPI !== 'undefined' && MetlinkAPI.get) {
      MetlinkAPI.get('/public/markets', { auth: false })
        .then(res => {
          const markets = (res && res.markets) || [];
          marketCountVal.textContent = String(markets.length);
        })
        .catch(() => {
          marketCountVal.textContent = '—';
        });
    } else {
      marketCountVal.textContent = '—';
    }
  }

  // 2. Animate circular SVG rings when scrolled into view
  const cards = problemSection.querySelectorAll('.lp-metric-card');
  cards.forEach(card => {
    observeOnce(card, (el) => {
      const ringFill = el.querySelector('.lp-ring-fill');
      const targetPercent = parseFloat(el.dataset.ringPercent || '100');
      const circumference = 251.32; // 2 * PI * 40
      const targetOffset = circumference - (circumference * targetPercent / 100);

      if (ringFill) {
        if (prefersReducedMotion()) {
          ringFill.style.transition = 'none';
          ringFill.style.strokeDashoffset = `${targetOffset}`;
        } else {
          ringFill.style.strokeDashoffset = `${targetOffset}`;
        }
      }
    }, 0.3);
  });
}

/**
 * Feature D: Sticky Stacking Cards with Scroll-Linked Depth
 */
function initStackCards() {
  const container = document.getElementById('lpStackContainer');
  if (!container) return;

  const wrappers = container.querySelectorAll('.lp-stack-card-wrapper');
  if (wrappers.length === 0) return;

  let ticking = false;

  function updateCardScales() {
    ticking = false;
    if (prefersReducedMotion()) {
      wrappers.forEach(w => {
        const card = w.querySelector('.lp-stack-card');
        if (card) {
          card.style.transform = 'none';
          card.style.opacity = '1';
        }
      });
      return;
    }

    const navOffset = 90;

    for (let i = 0; i < wrappers.length - 1; i++) {
      const currentWrapper = wrappers[i];
      const nextWrapper = wrappers[i + 1];
      const card = currentWrapper.querySelector('.lp-stack-card');
      if (!card) continue;

      const nextRect = nextWrapper.getBoundingClientRect();
      const currentRect = currentWrapper.getBoundingClientRect();

      // How close is the next card to sticking over the current one?
      const overlapStart = window.innerHeight * 0.8;
      const overlapEnd = navOffset + 80;

      if (nextRect.top < overlapStart) {
        const progress = Math.min(1, Math.max(0, (overlapStart - nextRect.top) / (overlapStart - overlapEnd)));
        const scale = 1 - (progress * 0.06); // scale down to 0.94
        const opacity = 1 - (progress * 0.12); // dim to 0.88
        card.style.transform = `scale(${scale})`;
        card.style.opacity = `${opacity}`;
      } else {
        card.style.transform = 'scale(1)';
        card.style.opacity = '1';
      }
    }
  }

  window.addEventListener('scroll', () => {
    if (!ticking) {
      window.requestAnimationFrame(updateCardScales);
      ticking = true;
    }
  }, { passive: true });

  updateCardScales();
}

/**
 * Feature E: Bilingual USSD Guide & Phone Screen Toggle
 */
function initUssdToggle() {
  const phoneScreen = document.getElementById('lpPhoneScreen');
  const instructionsContainer = document.getElementById('lpUssdInstructions');
  const langBtns = document.querySelectorAll('.lp-lang-btn');

  if (!phoneScreen || !instructionsContainer || langBtns.length === 0) return;

  const CONTENT = {
    en: {
      screen: `METLINK USSD *123#\n\n1. Register Harvest\n2. Kigali Market Prices\n3. Help & Support\n\nSelect option: [1]\n\nTomato Ripeness:\n1. Green (Firm)\n2. Turning (Pink/Orange)\n3. Ripe (Ready to eat)\nSelect: [3]\n\nHarvest Quantity (kg):\n[250]\n\nVentilated Storage ready?\n1. Yes  2. No\nSelect: [2]\n\nSubmission received!\nAdvice SMS arriving shortly.`,
      steps: [
        {
          title: 'Dial *123# on Any Mobile Phone',
          desc: 'Works on any basic feature phone across MTN and Airtel networks. No smartphone, mobile app, or internet connection required.'
        },
        {
          title: 'Select Harvest Registration',
          desc: 'Choose option 1 to report an upcoming harvest and indicate the ripeness stage of your crop: Green, Turning, or Ripe.'
        },
        {
          title: 'Enter Quantity & Storage Status',
          desc: 'Input your expected harvest volume in kilograms and specify whether ventilated crates or cooling shade are available.'
        },
        {
          title: 'Receive Instant Actionable SMS Advice',
          desc: 'Within seconds, METLINK sends an SMS with a clear decision: SELL NOW, STORE AND WAIT, or SEEK ALTERNATIVE MARKET with current Kigali prices.'
        }
      ]
    },
    rw: {
      screen: `METLINK USSD *123#\n\n1. Andikisha Umusaruro\n2. Ibiciro by'Amasoko i Kigali\n3. Ubufasha\n\nHitamo: [1]\n\nUko inyanya zimeze:\n1. Ibibisi (Green)\n2. Ibifite ibara (Turning)\n3. Ibihiye (Ripe)\nHitamo: [3]\n\nIngano y'umusaruro (kg):\n[250]\n\nUfite ububiko buhumeka?\n1. Yego  2. Oya\nHitamo: [2]\n\nUmusaruro wakiriwe!\nInama kuri SMS iraza mukanya.`,
      steps: [
        {
          title: 'Kanda *123# kuri Terefone Iyo Ari Yo Yose',
          desc: 'Bikora kuri terefone isanzwe yose ikoresha MTN cyangwa Airtel. Nta enterineti cyangwa terefone igezweho (smartphone) bikenewe.'
        },
        {
          title: 'Hitamo Kwandikisha Umusaruro',
          desc: 'Hitamo umubare 1 wandikishe umusaruro ugiye gusarura, ugaragaze niba inyanya ari ibibisi, izifite ibara, cyangwa izihiye.'
        },
        {
          title: 'Injiza Ibiro (kg) n\'Uburyo bwo Kubika',
          desc: 'Andika ibiro by\'inyanya uteganya gusarura hanyuma wemeze niba ufite uburyo bwo kuzibika ahantu hahumeka neza.'
        },
        {
          title: 'Akira Ubutumwa bw\'Inama Ifatika kuri SMS',
          desc: 'Mu masegonda make, uhita wakira SMS igufasha gufata umwanzuro: GURISHA NONAHA, BIKA UTEGEREZE, cyangwa SHAKA IRINDI SOKO.'
        }
      ]
    }
  };

  function setLanguage(lang) {
    const data = CONTENT[lang] || CONTENT.en;

    // Update phone screen with subtle fade
    phoneScreen.style.opacity = '0.3';
    setTimeout(() => {
      phoneScreen.textContent = data.screen;
      phoneScreen.style.opacity = '1';
    }, 150);

    // Update instruction steps safely via DOM nodes
    instructionsContainer.replaceChildren();
    const ol = document.createElement('ol');
    ol.className = 'lp-ussd-steps-list';

    data.steps.forEach(step => {
      const li = document.createElement('li');
      li.className = 'lp-ussd-step-item';

      const strong = document.createElement('strong');
      strong.textContent = step.title;

      const p = document.createElement('p');
      p.style.margin = '4px 0 0';
      p.textContent = step.desc;

      li.appendChild(strong);
      li.appendChild(p);
      ol.appendChild(li);
    });

    instructionsContainer.appendChild(ol);

    // Update toggle buttons aria-pressed
    langBtns.forEach(btn => {
      const btnLang = btn.dataset.lang;
      btn.setAttribute('aria-pressed', btnLang === lang ? 'true' : 'false');
    });

    // Save preference
    try {
      localStorage.setItem('metlink_landing_lang', lang);
    } catch (e) {}
  }

  langBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const selected = btn.dataset.lang;
      if (selected) setLanguage(selected);
    });
  });

  // Restore saved choice or default English
  let initialLang = 'en';
  try {
    const saved = localStorage.getItem('metlink_landing_lang');
    if (saved === 'en' || saved === 'rw') initialLang = saved;
  } catch (e) {}

  setLanguage(initialLang);
}

/**
 * Feature F: Interactive Market Insights Horizontal Bar Chart
 */
function initMarketChart() {
  const chartWrapper = document.getElementById('lpMarketChartContainer');
  const loadingEl = document.getElementById('lpMarketLoading');
  const emptyEl = document.getElementById('lpMarketEmpty');
  const errorEl = document.getElementById('lpMarketError');
  const retryBtn = document.getElementById('lpMarketRetryBtn');
  const updatedEl = document.getElementById('lpMarketUpdated');

  if (!chartWrapper) return;

  function showState(state) {
    if (loadingEl) loadingEl.style.display = state === 'loading' ? 'block' : 'none';
    if (emptyEl) emptyEl.style.display = state === 'empty' ? 'block' : 'none';
    if (errorEl) errorEl.style.display = state === 'error' ? 'block' : 'none';
    if (chartWrapper) chartWrapper.style.display = state === 'data' ? 'block' : 'none';
  }

  function getDemandBadgeClass(level) {
    const norm = (level || '').toUpperCase();
    if (norm === 'HIGH') return 'badge badge-success badge-demand badge-demand-high';
    if (norm === 'MEDIUM') return 'badge badge-warning badge-demand badge-demand-medium';
    if (norm === 'LOW') return 'badge badge-danger badge-demand badge-demand-low';
    return 'badge badge-info badge-demand';
  }

  function formatPrice(val) {
    const num = Number(val);
    return isNaN(num) ? '—' : `${Math.round(num)} RWF/kg`;
  }

  function renderChart(markets) {
    chartWrapper.replaceChildren();

    if (!markets || markets.length === 0) {
      showState('empty');
      return;
    }

    // Sort markets from highest to lowest price
    const sorted = [...markets].sort((a, b) => {
      const priceA = Number(a.average_price_per_kg) || 0;
      const priceB = Number(b.average_price_per_kg) || 0;
      return priceB - priceA;
    });

    const maxPrice = Math.max(...sorted.map(m => Number(m.average_price_per_kg) || 0), 1);

    const ul = document.createElement('ul');
    ul.className = 'lp-chart-list';

    sorted.forEach(market => {
      const li = document.createElement('li');
      li.className = 'lp-chart-row';
      li.setAttribute('tabindex', '0');
      li.setAttribute('role', 'listitem');

      const marketName = market.market_name || 'Market';
      const location = market.location || '';
      const price = Number(market.average_price_per_kg) || 0;
      const demand = (market.demand_level || 'NORMAL').toUpperCase();

      li.setAttribute('aria-label', `${marketName}, ${location}, ${price} RWF per kg, demand ${demand}`);

      // 1. Market Name and Location
      const infoDiv = document.createElement('div');
      infoDiv.className = 'lp-market-info';

      const nameSpan = document.createElement('span');
      nameSpan.className = 'lp-market-name';
      nameSpan.textContent = marketName;

      const locSpan = document.createElement('span');
      locSpan.className = 'lp-market-loc';
      locSpan.textContent = location;

      infoDiv.appendChild(nameSpan);
      infoDiv.appendChild(locSpan);

      // 2. Center Bar Track
      const trackDiv = document.createElement('div');
      trackDiv.className = 'lp-bar-track';

      const fillDiv = document.createElement('div');
      fillDiv.className = 'lp-bar-fill';
      fillDiv.dataset.targetWidth = `${(price / maxPrice) * 100}%`;

      const valSpan = document.createElement('span');
      valSpan.className = 'lp-bar-value';
      valSpan.textContent = formatPrice(price);

      trackDiv.appendChild(fillDiv);
      trackDiv.appendChild(valSpan);

      // 3. Right Demand Badge
      const badgeWrap = document.createElement('div');
      badgeWrap.className = 'lp-badge-wrap';

      const badge = document.createElement('span');
      badge.className = getDemandBadgeClass(demand);
      badge.textContent = demand;

      badgeWrap.appendChild(badge);

      li.appendChild(infoDiv);
      li.appendChild(trackDiv);
      li.appendChild(badgeWrap);
      ul.appendChild(li);
    });

    chartWrapper.appendChild(ul);
    showState('data');

    // Trigger entrance animation with IntersectionObserver
    observeOnce(chartWrapper, () => {
      const bars = chartWrapper.querySelectorAll('.lp-bar-fill');
      bars.forEach(bar => {
        const target = bar.dataset.targetWidth || '0%';
        if (prefersReducedMotion()) {
          bar.style.transition = 'none';
          bar.style.width = target;
        } else {
          bar.style.width = target;
        }
      });
    }, 0.2);

    // Show latest update date if valid date is present in data
    if (updatedEl && sorted[0] && sorted[0].created_at) {
      try {
        const d = new Date(sorted[0].created_at);
        if (!isNaN(d.getTime())) {
          updatedEl.textContent = `Latest update: ${d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}`;
          updatedEl.style.display = 'block';
        } else {
          updatedEl.style.display = 'none';
        }
      } catch (e) {
        updatedEl.style.display = 'none';
      }
    }
  }

  async function fetchMarkets() {
    showState('loading');
    if (typeof MetlinkAPI === 'undefined' || !MetlinkAPI.get) {
      showState('error');
      return;
    }

    try {
      const res = await MetlinkAPI.get('/public/markets', { auth: false, noAuthRedirect: true });
      if (res && Array.isArray(res.markets)) {
        renderChart(res.markets);
      } else {
        showState('error');
      }
    } catch (err) {
      showState('error');
    }
  }

  if (retryBtn) {
    retryBtn.addEventListener('click', () => {
      fetchMarkets();
    });
  }

  fetchMarkets();
}

/**
 * Feature G: Copyright Current Year
 */
function initYear() {
  const yearEl = document.getElementById('lpCurrentYear');
  if (yearEl) {
    yearEl.textContent = String(new Date().getFullYear());
  }
}

/**
 * DOMContentLoaded Orchestrator
 */
document.addEventListener('DOMContentLoaded', () => {
  initNav();
  initCarousel();
  initRings();
  initStackCards();
  initUssdToggle();
  initMarketChart();
  initYear();
});
